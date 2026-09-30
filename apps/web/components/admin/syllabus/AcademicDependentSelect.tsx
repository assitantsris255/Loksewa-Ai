'use client';

import { useState, useEffect } from 'react';
import { adminSyllabusApi } from '@/lib/api/admin-syllabus';

interface AcademicDependentSelectProps {
  category?: number | string | null;
  position?: number | string | null;
  subject?: number | string | null;
  chapter?: number | string | null;
  topic?: number | string | null;
  onChange: (field: string, value: any) => void;
  maxLevel?: 'category' | 'position' | 'subject' | 'chapter' | 'topic';
  requiredLevels?: ('category' | 'position' | 'subject' | 'chapter' | 'topic')[];
  errors?: Record<string, string>;
  layout?: 'vertical' | 'grid';
  labels?: Record<string, string>;
}

export function AcademicDependentSelect({
  category,
  position,
  subject,
  chapter,
  topic,
  onChange,
  maxLevel = 'topic',
  requiredLevels = ['category', 'position', 'subject'],
  errors = {},
  layout = 'grid',
  labels = {}
}: AcademicDependentSelectProps) {
  const [tree, setTree] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [subjects, setSubjects] = useState<any[]>([]);
  const [chapters, setChapters] = useState<any[]>([]);
  const [topics, setTopics] = useState<any[]>([]);
  const [loading, setLoading] = useState<Record<string, boolean>>({ tree: true });

  const levels = ['category', 'position', 'subject', 'chapter', 'topic'];
  const maxIdx = levels.indexOf(maxLevel);
  const show = (lvl: string) => levels.indexOf(lvl) <= maxIdx;
  const isRequired = (lvl: 'category' | 'position' | 'subject' | 'chapter' | 'topic') =>
    requiredLevels.includes(lvl);
  const hasOption = (options: any[], value?: number | string | null) =>
    value != null && options.some(option => String(option.id) === String(value));
  const pendingValue = (options: any[], value: number | string | null | undefined) =>
    value != null && !hasOption(options, value) ? String(value) : undefined;

  const pendingCategory = pendingValue(categories, category);
  const pendingPosition = pendingValue(positions, position);
  const pendingSubject = pendingValue(subjects, subject);
  const pendingChapter = pendingValue(chapters, chapter);
  const pendingTopic = pendingValue(topics, topic);

  const flattenPositionNodes = (nodes: any[] = [], acc: any[] = []): any[] => {
    for (const node of nodes) {
      acc.push(node);
      if (Array.isArray(node.children) && node.children.length > 0) {
        flattenPositionNodes(node.children, acc);
      }
    }
    return acc;
  };

  const findPositionSubjects = (nodes: any[] = []): any[] => {
    const found: any[] = [];
    const walk = (items: any[]) => {
      for (const item of items) {
        const subjects = ((item.papers || []) as any[]).flatMap((paper: any) => paper.subjects || []);
        found.push(...subjects);
        if (Array.isArray(item.children) && item.children.length > 0) walk(item.children);
      }
    };
    walk(nodes);
    return found;
  };

  const findSubjectChapters = (nodes: any[] = [], subjectId: number): any[] => {
    for (const node of nodes) {
      for (const paper of (node.papers || []) as any[]) {
        for (const sub of (paper.subjects || []) as any[]) {
          if (Number(sub.id) === Number(subjectId)) {
            return sub.chapters || [];
          }
        }
      }
      if (Array.isArray(node.children) && node.children.length > 0) {
        const nested = findSubjectChapters(node.children, subjectId);
        if (nested.length > 0) return nested;
      }
    }
    return [];
  };

  const collectPositionChapters = (nodes: any[] = []): any[] => {
    const found: any[] = [];
    const walk = (items: any[]) => {
      for (const item of items) {
        for (const paper of (item.papers || []) as any[]) {
          for (const sub of (paper.subjects || []) as any[]) {
            found.push(...(sub.chapters || []));
          }
        }
        if (Array.isArray(item.children) && item.children.length > 0) walk(item.children);
      }
    };
    walk(nodes);
    return found;
  };

  const findChapterTopics = (nodes: any[] = [], chapterId: number): any[] => {
    for (const node of nodes) {
      for (const paper of (node.papers || []) as any[]) {
        for (const sub of (paper.subjects || []) as any[]) {
          for (const chap of (sub.chapters || []) as any[]) {
            if (Number(chap.id) === Number(chapterId)) {
              return chap.topics || [];
            }
          }
        }
      }
      if (Array.isArray(node.children) && node.children.length > 0) {
        const nested = findChapterTopics(node.children, chapterId);
        if (nested.length > 0) return nested;
      }
    }
    return [];
  };

  // 1. Load full academic hierarchy tree in ONE fast cached request
  useEffect(() => {
    let isMounted = true;
    setLoading(prev => ({ ...prev, tree: true, category: true }));

    adminSyllabusApi.getTreeCached()
      .then((treeData: any[]) => {
        if (!isMounted) return;
        const validTree = Array.isArray(treeData) ? treeData : [];
        setTree(validTree);
        setCategories(
          validTree.map(c => ({
            id: c.id,
            name: c.name,
            order: c.order,
            is_active: c.is_active,
          }))
        );
      })
      .catch((err) => {
        console.error('Failed to load academic tree, falling back to individual calls:', err);
        return adminSyllabusApi.getCategories()
          .then((res: any) => {
            if (isMounted) setCategories(Array.isArray(res) ? res : (res?.results || []));
          })
          .catch(console.error);
      })
      .finally(() => {
        if (isMounted) setLoading(prev => ({ ...prev, tree: false, category: false }));
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Positions derived from selected Category (instant from tree, fallback to API)
  useEffect(() => {
    if (!category) {
      setPositions([]);
      return;
    }
    const catId = Number(category);
    const catNode = tree.find(c => c.id === catId);
    if (catNode && Array.isArray(catNode.positions) && catNode.positions.length > 0) {
      setPositions(flattenPositionNodes(catNode.positions));
    } else if (!loading.tree) {
      setLoading(prev => ({ ...prev, position: true }));
      adminSyllabusApi.getPositions(catId)
        .then((res: any) => setPositions(Array.isArray(res) ? res : (res?.results || [])))
        .catch(console.error)
        .finally(() => setLoading(prev => ({ ...prev, position: false })));
    }
  }, [category, tree, loading.tree]);

  // 3. Subjects derived from selected Position (instant from tree, fallback to API)
  useEffect(() => {
    if (!position) {
      setSubjects([]);
      return;
    }
    const posId = Number(position);
    let foundSubjects: any[] = [];

    for (const cat of tree) {
      const nestedPositions = flattenPositionNodes(cat.positions || []);
      const matchedPosition = nestedPositions.find(pos => pos.id === posId);
      if (matchedPosition) {
        foundSubjects = findPositionSubjects([matchedPosition]);
        break;
      }
    }

    if (foundSubjects.length > 0) {
      const unique = Array.from(new Map(foundSubjects.map(s => [s.id, s])).values());
      setSubjects(unique);
    } else if (!loading.tree) {
      setLoading(prev => ({ ...prev, subject: true }));
      adminSyllabusApi.getSubjects(posId)
        .then((res: any) => setSubjects(Array.isArray(res) ? res : (res?.results || [])))
        .catch(console.error)
        .finally(() => setLoading(prev => ({ ...prev, subject: false })));
    }
  }, [position, tree, loading.tree]);

  // 4. Chapters derived from selected Subject (instant from tree, fallback to API)
  // When subject is optional and not selected, load chapters from the full position.
  useEffect(() => {
    if (!subject && !position) {
      setChapters([]);
      return;
    }
    if (subject) {
      const subId = Number(subject);
      let foundChapters: any[] = [];

      for (const cat of tree) {
        const nestedPositions = flattenPositionNodes(cat.positions || []);
        const related = findSubjectChapters(nestedPositions, subId);
        if (related.length > 0) {
          foundChapters = related;
          break;
        }
      }

      if (foundChapters.length > 0) {
        setChapters(foundChapters);
      } else if (!loading.tree) {
        setLoading(prev => ({ ...prev, chapter: true }));
        adminSyllabusApi.getChapters(subId)
          .then((res: any) => setChapters(Array.isArray(res) ? res : (res?.results || [])))
          .catch(console.error)
          .finally(() => setLoading(prev => ({ ...prev, chapter: false })));
      }
    } else {
      // Subject is optional and not selected — load all chapters for the position.
      const posId = Number(position);
      let allChapters: any[] = [];
      for (const cat of tree) {
        const nestedPositions = flattenPositionNodes(cat.positions || []);
        const matchedPosition = nestedPositions.find(pos => pos.id === posId);
        if (matchedPosition) {
          allChapters = collectPositionChapters([matchedPosition]);
          break;
        }
      }
      if (allChapters.length > 0) {
        setChapters(allChapters);
      } else {
        setChapters([]);
      }
    }
  }, [subject, position, tree, loading.tree]);

  // 5. Topics derived from selected Chapter (instant from tree, fallback to API)
  useEffect(() => {
    if (!chapter) {
      setTopics([]);
      return;
    }
    const chapId = Number(chapter);
    let foundTopics: any[] = [];

    for (const cat of tree) {
      const nestedPositions = flattenPositionNodes(cat.positions || []);
      const related = findChapterTopics(nestedPositions, chapId);
      if (related.length > 0) {
        foundTopics = related;
        break;
      }
    }

    if (foundTopics.length > 0) {
      setTopics(foundTopics);
    } else if (!loading.tree) {
      setLoading(prev => ({ ...prev, topic: true }));
      adminSyllabusApi.getTopics(chapId)
        .then((res: any) => setTopics(Array.isArray(res) ? res : (res?.results || [])))
        .catch(console.error)
        .finally(() => setLoading(prev => ({ ...prev, topic: false })));
    }
  }, [chapter, tree, loading.tree]);

  const handleChange = (field: string, val: string) => {
    const value = val ? Number(val) : undefined;
    // Only emit a single onChange call per user interaction.
    // The parent component (e.g. QuestionSetForm / handleAcademicChange) is
    // responsible for cascading child-field resets when a parent field changes.
    // Emitting multiple onChange calls here caused a stale-closure bug: each
    // call read from the same stale `data` snapshot in the parent, so the last
    // "reset" call would silently overwrite the category value that was just set.
    onChange(field, value);
  };

  const containerClass = layout === 'grid' 
    ? 'grid grid-cols-1 md:grid-cols-2 gap-6' 
    : 'space-y-6';

  return (
    <div className={containerClass}>
      {/* 1. Category */}
      {show('category') && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {labels.category || 'Category'} {isRequired('category') && <span className="text-red-500">*</span>}
          </label>
          <select
            value={category == null ? '' : String(category)}
            onChange={e => handleChange('category', e.target.value)}
            className={`w-full p-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 ${errors.category ? 'border-red-500' : 'border-gray-200'}`}
          >
            {pendingCategory != null && <option value={pendingCategory} disabled>{loading.tree || loading.category ? `Loading selected category (#${category})...` : `Selected category unavailable (#${category})`}</option>}
            <option value="">
              {loading.category ? 'Loading categories...' : 'Select Category'}
            </option>
            {categories.map(c => (
              <option key={c.id} value={String(c.id)}>{c.name}</option>
            ))}
          </select>
          {loading.category && <p className="text-xs text-gray-400 mt-1">Loading categories...</p>}
          {errors.category && <p className="text-red-500 text-xs mt-1">{errors.category}</p>}
        </div>
      )}

      {/* 2. Position / Level */}
      {show('position') && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {labels.position || 'Position / Level'} {isRequired('position') && <span className="text-red-500">*</span>}
          </label>
          <select
            value={position == null ? '' : String(position)}
            onChange={e => handleChange('position', e.target.value)}
            disabled={!category || loading.position}
            className={`w-full p-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 ${errors.exam || errors.position ? 'border-red-500' : 'border-gray-200'} ${!category ? 'bg-gray-50 text-gray-400' : ''}`}
          >
            {pendingPosition != null && <option value={pendingPosition} disabled>{loading.tree || loading.position ? `Loading selected position (#${position})...` : `Selected position unavailable (#${position})`}</option>}
            <option value="">
              {!category
                ? 'Select Category first'
                : loading.position
                ? 'Loading positions...'
                : 'Select Position'}
            </option>
            {positions.map(positionNode => (
              <option key={positionNode.id} value={String(positionNode.id)}>
                {positionNode.name}
              </option>
            ))}
          </select>
          {loading.position && <p className="text-xs text-gray-400 mt-1">Loading positions...</p>}
          {(errors.exam || errors.position) && <p className="text-red-500 text-xs mt-1">{errors.exam || errors.position}</p>}
        </div>
      )}

      {/* 3. Subject */}
      {show('subject') && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {labels.subject || 'Subject'}{' '}
            {isRequired('subject') ? (
              <span className="text-red-500">*</span>
            ) : (
              <span className="text-xs text-gray-400 font-normal">(Optional)</span>
            )}
          </label>
          <select
            value={subject == null ? '' : String(subject)}
            onChange={e => handleChange('subject', e.target.value)}
            disabled={!position || loading.subject}
            className={`w-full p-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 ${errors.subject ? 'border-red-500' : 'border-gray-200'} ${!position ? 'bg-gray-50 text-gray-400' : ''}`}
          >
            {pendingSubject != null && <option value={pendingSubject} disabled>{loading.tree || loading.subject ? `Loading selected subject (#${subject})...` : `Selected subject unavailable (#${subject})`}</option>}
            <option value="">
              {!position
                ? 'Select Position first'
                : loading.subject
                ? 'Loading subjects...'
                : subjects.length === 0
                ? 'No subjects available'
                : isRequired('subject')
                ? 'Select Subject'
                : 'Select Subject (Optional)'}
            </option>
            {subjects.map(s => (
              <option key={s.id} value={String(s.id)}>{s.name}</option>
            ))}
          </select>
          {loading.subject && <p className="text-xs text-gray-400 mt-1">Loading subjects...</p>}
          {errors.subject && <p className="text-red-500 text-xs mt-1">{errors.subject}</p>}
        </div>
      )}

      {/* 4. Chapter / Unit (Optional) */}
      {show('chapter') && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {labels.chapter || 'Chapter / Unit'}{' '}
            {isRequired('chapter') ? (
              <span className="text-red-500">*</span>
            ) : (
              <span className="text-xs text-gray-400 font-normal">(Optional)</span>
            )}
          </label>
          <select
            value={chapter == null ? '' : String(chapter)}
            onChange={e => handleChange('chapter', e.target.value)}
            disabled={(!subject && isRequired('subject')) || loading.chapter || !position}
            className={`w-full p-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 ${errors.unit || errors.chapter ? 'border-red-500' : 'border-gray-200'} ${(!subject && isRequired('subject')) || !position ? 'bg-gray-50 text-gray-400' : ''}`}
          >
            {pendingChapter != null && <option value={pendingChapter} disabled>{loading.tree || loading.chapter ? `Loading selected chapter (#${chapter})...` : `Selected chapter unavailable (#${chapter})`}</option>}
            <option value="">
              {!position
                ? 'Select Position first'
                : !subject && isRequired('subject')
                ? 'Select Subject first'
                : loading.chapter
                ? 'Loading chapters...'
                : chapters.length === 0
                ? 'No chapters available'
                : isRequired('chapter')
                ? 'Select Chapter'
                : 'Select Chapter (Optional)'}
            </option>
            {chapters.map(c => (
              <option key={c.id} value={String(c.id)}>{c.title || c.name}</option>
            ))}
          </select>
          {loading.chapter && <p className="text-xs text-gray-400 mt-1">Loading chapters...</p>}
          {(errors.unit || errors.chapter) && <p className="text-red-500 text-xs mt-1">{errors.unit || errors.chapter}</p>}
        </div>
      )}

      {/* 5. Topic (Optional - enabled only if chapter selected) */}
      {show('topic') && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {labels.topic || 'Topic'}{' '}
            {isRequired('topic') ? (
              <span className="text-red-500">*</span>
            ) : (
              <span className="text-xs text-gray-400 font-normal">(Optional)</span>
            )}
          </label>
          <select
            value={topic == null ? '' : String(topic)}
            onChange={e => handleChange('topic', e.target.value)}
            disabled={!chapter || loading.topic}
            className={`w-full p-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 ${errors.topic ? 'border-red-500' : 'border-gray-200'} ${!chapter ? 'bg-gray-50 text-gray-400' : ''}`}
          >
            {pendingTopic != null && <option value={pendingTopic} disabled>{loading.tree || loading.topic ? `Loading selected topic (#${topic})...` : `Selected topic unavailable (#${topic})`}</option>}
            <option value="">
              {!chapter
                ? 'Select Chapter first'
                : loading.topic
                ? 'Loading topics...'
                : topics.length === 0
                ? 'No topics available'
                : isRequired('topic')
                ? 'Select Topic'
                : 'Select Topic (Optional)'}
            </option>
            {topics.map(t => (
              <option key={t.id} value={String(t.id)}>{t.name}</option>
            ))}
          </select>
          {loading.topic && <p className="text-xs text-gray-400 mt-1">Loading topics...</p>}
          {errors.topic && <p className="text-red-500 text-xs mt-1">{errors.topic}</p>}
        </div>
      )}
    </div>
  );
}
