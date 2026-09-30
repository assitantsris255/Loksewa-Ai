from django.db import models
from core.models import User
from marketplace.models import PaymentMethod
from datetime import timedelta
from django.utils import timezone
from core.upload_validators import validate_image_size_5mb, validate_image_extension

class SubscriptionPlan(models.Model):
    DURATION_UNIT_CHOICES = (
        ('DAYS', 'Days'),
        ('WEEKS', 'Weeks'),
        ('MONTHS', 'Months'),
        ('YEAR', 'Year'),
    )

    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('ARCHIVED', 'Archived'),
    )

    BADGE_CHOICES = (
        ('NONE', 'None'),
        ('POPULAR', 'Popular'),
        ('BEST_VALUE', 'Best Value'),
        ('RECOMMENDED', 'Recommended'),
        ('LIMITED_OFFER', 'Limited Offer'),
    )

    PACKAGE_TYPE_CHOICES = (
        ('SINGLE', 'Single Preparation'),
        ('MULTI', 'Multi Preparation'),
        ('BUNDLE', 'Bundle'),
        ('ALL_ACCESS', 'All Access'),
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration = models.IntegerField()
    duration_unit = models.CharField(max_length=20, choices=DURATION_UNIT_CHOICES, default='DAYS')

    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Discount percentage")

    badge = models.CharField(max_length=20, choices=BADGE_CHOICES, default='NONE')

    # Feature access configuration
    features = models.JSONField(default=list, blank=True, help_text="List of string feature keys this plan unlocks")

    # Which course this plan grants enrollment access to (optional)
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='subscription_plans',
        help_text='Legacy/Single: The Course this plan grants enrollment access to. When payment is approved, student is enrolled in this course.'
    )

    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES, default='SINGLE', help_text="Type of package dictating the access rules.")
    
    eligible_courses = models.ManyToManyField(
        'courses.Course', 
        blank=True, 
        related_name='eligible_plans',
        help_text="Courses this package can grant access to. Used for MULTI and BUNDLE types."
    )

    # Flexible Preparation Pricing
    allowed_preparation_count = models.IntegerField(default=1, help_text="Number of preparations allowed for this plan (used for MULTI packages)")
    is_flexible = models.BooleanField(default=False, help_text="Deprecated: Use package_type='MULTI'. If true, the student can pick up to `allowed_preparation_count` courses.")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    display_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.price}"


class Subscription(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    )
    SOURCE_CHOICES = (
        ('CUSTOMER_PAYMENT', 'Customer Payment'),
        ('ADMIN_GRANT', 'Admin Grant'),
    )
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='CUSTOMER_PAYMENT')
    admin_grant_reason = models.TextField(blank=True, default='')
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='granted_subscriptions'
    )
    start_date = models.DateTimeField()
    expiry_date = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - {self.plan.name} ({self.status}) [{self.source}]"
        
    @property
    def is_active(self):
        return self.status == 'ACTIVE' and self.expiry_date > timezone.now()

class SubscriptionPayment(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    )
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscription_payments')
    subscription = models.OneToOneField(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment')
    
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='subscription_payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=255, unique=True)
    
    screenshot = models.ImageField(
        upload_to='subscriptions/payment_proofs/',
        validators=[validate_image_size_5mb, validate_image_extension],
    )
    note = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    rejection_reason = models.TextField(blank=True)
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_subscription_payments')

    def __str__(self):
        return f"{self.student.username} - {self.plan.name} - {self.status}"


class Invoice(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    payment = models.OneToOneField(SubscriptionPayment, on_delete=models.CASCADE, related_name='invoice')
    receipt_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.receipt_number


class SubscriptionCourseSelection(models.Model):
    """
    Records exactly which Course(s) a student selected for a
    MULTI/BUNDLE-type SubscriptionPlan.
    Supports both normal customer payments (linked to SubscriptionPayment)
    and admin-granted access (linked directly to Subscription).
    """
    payment = models.ForeignKey(
        SubscriptionPayment,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='course_selections',
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='course_selections',
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='subscription_selections',
    )
    selected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['selected_at']
        constraints = [
            models.UniqueConstraint(
                fields=['payment', 'course'],
                condition=models.Q(payment__isnull=False),
                name='unique_payment_course_selection'
            ),
            models.UniqueConstraint(
                fields=['subscription', 'course'],
                condition=models.Q(subscription__isnull=False),
                name='unique_subscription_course_selection'
            ),
        ]

    def __str__(self):
        user_str = self.subscription.student.username if self.subscription else (self.payment.student.username if self.payment else "Unknown")
        ref_str = f"sub #{self.subscription_id}" if self.subscription_id else f"payment #{self.payment_id}"
        return f"{user_str} → {self.course.title} ({ref_str})"
