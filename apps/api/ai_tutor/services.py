import os
from google import genai
from google.genai import types
from django.conf import settings
from .models import Message

# Try to get API key from environment, else use a placeholder or None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

class AITutorService:
    def __init__(self):
        self.is_mock = not bool(GEMINI_API_KEY)
        if not self.is_mock:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
        else:
            self.client = None
            
        self.model_name = 'gemini-2.5-flash'
        self.last_token_count = 0

    def construct_system_prompt(self, conversation):
        """Constructs the system prompt from admin-editable database content:
        AdminSettings.ai_tutor_base_prompt (shared prefix) + the PromptTemplate
        row for this conversation's mode (mode-specific suffix)."""
        from core.models import AdminSettings
        from .models import PromptTemplate

        base_prompt = AdminSettings.get_settings().ai_tutor_base_prompt

        try:
            mode_prompt = PromptTemplate.objects.get(mode=conversation.mode).prompt_text
        except PromptTemplate.DoesNotExist:
            mode_prompt = PromptTemplate.MODE_DEFAULTS.get(conversation.mode, '')

        return base_prompt + mode_prompt

    # Common English words excluded from keyword matching so retrieval scores
    # on meaningful terms rather than connective/filler words.
    _STOPWORDS = frozenset([
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'who', 'when',
        'where', 'why', 'how', 'does', 'do', 'did', 'can', 'could', 'should',
        'would', 'and', 'or', 'but', 'for', 'with', 'about', 'this', 'that',
        'these', 'those', 'you', 'your', 'please', 'explain', 'tell', 'me',
        'to', 'of', 'in', 'on', 'it', 'be', 'i', 'my',
    ])

    MAX_KNOWLEDGE_MATCHES = 2
    MAX_EXCERPT_CHARS = 800

    def retrieve_knowledge_context(self, question_text, student=None):
        """Keyword-matches the student's question against admin-curated
        StudyMaterial content (status='published', available_to_ai_tutor=True)
        and returns a formatted reference block, or '' if nothing matches.

        Deliberately keyword-based rather than embedding-based: no extra
        provider API calls or vector store needed, everything is a plain
        database query. Filtered to courses the requesting student is entitled to.
        """
        from notes.models import StudyMaterial
        from courses.services.course_access_service import CourseAccessService
        import re

        words = re.findall(r"[a-zA-Z]{4,}", question_text.lower())
        keywords = [w for w in words if w not in self._STOPWORDS]
        if not keywords:
            return ''

        candidates = StudyMaterial.objects.filter(
            status='published', available_to_ai_tutor=True
        ).exclude(content='')

        if student:
            candidates = CourseAccessService.filter_notes_queryset(student, candidates)

        scored = []
        for material in candidates:
            haystack = f"{material.title} {material.content}".lower()
            score = sum(haystack.count(kw) for kw in keywords)
            if score > 0:
                scored.append((score, material))

        if not scored:
            return ''

        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_matches = scored[:self.MAX_KNOWLEDGE_MATCHES]

        blocks = []
        for _, material in top_matches:
            excerpt = material.content[:self.MAX_EXCERPT_CHARS]
            blocks.append(f"### {material.title}\n{excerpt}")

        return (
            "\n\nReference material curated by the admin team (use it to ground your "
            "answer when relevant, but do not claim it is the only source):\n\n"
            + "\n\n".join(blocks)
        )

    def generate_response(self, conversation, new_user_message_content):
        """Generates a response from the AI provider."""
        if self.is_mock:
            return self._generate_mock_response(conversation, new_user_message_content)

        # Retrieve previous messages for context
        previous_messages = conversation.messages.all().order_by('created_at')
        
        # Build the conversation history for the Gemini API
        chat_history = []
        for msg in previous_messages:
            if msg.role == 'system':
                continue
            gemini_role = 'user' if msg.role == 'user' else 'model'
            chat_history.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=msg.content)]))

        system_prompt = self.construct_system_prompt(conversation)
        student = getattr(conversation, 'student', None)
        system_prompt += self.retrieve_knowledge_context(new_user_message_content, student=student)


        try:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7
            )
            chat = self.client.chats.create(model=self.model_name, config=config)
            
            # Send history if supported or just send message
            # For simplicity, we just send message. If history is needed, we would initialize chat with history.
            if chat_history:
                # The google-genai Python SDK uses `history` kwarg in create()
                chat = self.client.chats.create(model=self.model_name, config=config, history=chat_history)
            
            response = chat.send_message(new_user_message_content)
            if response.usage_metadata and response.usage_metadata.total_token_count:
                self.last_token_count = response.usage_metadata.total_token_count
            return response.text
        except Exception as e:
            print(f"AI Provider Error: {e}")
            try:
                from core.notification_service import NotificationService
                NotificationService.notify_system_failure(
                    component='AI Tutor Provider',
                    detail=f"Gemini API call failed for {conversation.student.username}: {e}",
                    action_url='/admin-dashboard/ai-tutor/overview',
                )
            except Exception:
                # Never let the notification path itself break the student's
                # response - they still need the fallback message below.
                pass
            return "AI Tutor is temporarily unavailable due to a provider error. Please try again later."

    def _generate_mock_response(self, conversation, new_user_message_content):
        """Generates a mock response when no API key is present."""
        return (
            "⚠️ **AI Tutor Configuration Missing**\n\n"
            "The AI Tutor is currently running in mock mode because the `GEMINI_API_KEY` environment variable is not set. "
            "Please configure the API key on the backend to interact with the real AI.\n\n"
            f"**You said:** {new_user_message_content}\n"
            f"**Mode:** {conversation.get_mode_display()}"
        )

import json

class AdminAILogic:
    def __init__(self):
        self.is_mock = not bool(GEMINI_API_KEY)
        if not self.is_mock:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = 'gemini-2.5-flash'
        
    def generate_options(self, question_text, subject):
        """Generate options A, B, C, D and correct_answer for a given question."""
        if self.is_mock:
            return {
                "option_a": "Generated Option A",
                "option_b": "Generated Option B",
                "option_c": "Generated Option C",
                "option_d": "Generated Option D",
                "correct_answer": "A"
            }
            
        prompt = f"""
        You are an expert examiner for Nepal Loksewa exams.
        Subject: {subject}
        Question: {question_text}
        
        Generate 4 plausible multiple choice options (A, B, C, D) and specify which one is correct.
        Keep options concise and relevant. Provide the output strictly in JSON format matching the schema exactly.
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "option_a": {"type": "STRING"},
                            "option_b": {"type": "STRING"},
                            "option_c": {"type": "STRING"},
                            "option_d": {"type": "STRING"},
                            "correct_answer": {"type": "STRING", "enum": ["A", "B", "C", "D"]}
                        },
                        "required": ["option_a", "option_b", "option_c", "option_d", "correct_answer"]
                    },
                    temperature=0.3
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"AdminAILogic error: {e}")
            return None

    def generate_bulk_content(self, questions, generate_options: bool, generate_explanations: bool, subject: str):
        """Generate options and/or explanations for a batch of questions."""
        if self.is_mock:
            # Return mock data
            for q in questions:
                if generate_options:
                    q['option_a'] = "Generated A"
                    q['option_b'] = "Generated B"
                    q['option_c'] = "Generated C"
                    q['option_d'] = "Generated D"
                    q['correct_answer'] = "A"
                if generate_explanations:
                    q['explanation'] = "Generated explanation."
            return questions

        prompt = f"""
        You are an expert examiner for Nepal Loksewa exams.
        Subject: {subject}
        
        I will provide a JSON list of questions. For each question, please generate the missing content.
        If generate_options is requested, generate 4 plausible multiple choice options (A, B, C, D) and specify which one is correct.
        If generate_explanations is requested, generate a concise explanation for the correct answer.
        
        Tasks requested:
        Generate Options: {generate_options}
        Generate Explanations: {generate_explanations}
        
        Questions Data:
        {json.dumps(questions, indent=2)}
        
        Provide the output strictly in JSON format as a list of objects, preserving the original 'id' for each question.
        """
        
        schema = {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"}
                },
                "required": ["id"]
            }
        }
        
        if generate_options:
            schema["items"]["properties"].update({
                "option_a": {"type": "STRING"},
                "option_b": {"type": "STRING"},
                "option_c": {"type": "STRING"},
                "option_d": {"type": "STRING"},
                "correct_answer": {"type": "STRING", "enum": ["A", "B", "C", "D"]}
            })
        
        if generate_explanations:
            schema["items"]["properties"].update({
                "explanation": {"type": "STRING"}
            })

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.3
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"AdminAILogic bulk error: {e}")
            return None
