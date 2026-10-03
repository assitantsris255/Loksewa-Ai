from rest_framework import serializers
from administration.models import TrashItem, DatabaseBackup


class TrashItemSerializer(serializers.ModelSerializer):
    deleted_by_name = serializers.SerializerMethodField()
    restored_by_name = serializers.SerializerMethodField()
    permanent_deleted_by_name = serializers.SerializerMethodField()

    def get_deleted_by_name(self, obj):
        if not obj.deleted_by:
            return "System / Unknown"
        return obj.deleted_by.get_full_name() or obj.deleted_by.username

    def get_restored_by_name(self, obj):
        if not obj.restored_by:
            return None
        return obj.restored_by.get_full_name() or obj.restored_by.username

    def get_permanent_deleted_by_name(self, obj):
        if not obj.permanent_deleted_by:
            return None
        return obj.permanent_deleted_by.get_full_name() or obj.permanent_deleted_by.username

    class Meta:
        model = TrashItem
        fields = [
            'id', 'app_label', 'model_name', 'object_id', 'title',
            'item_type', 'module', 'deleted_by', 'deleted_by_name',
            'deleted_at', 'reason', 'details', 'is_restored',
            'restored_at', 'restored_by', 'restored_by_name',
            'is_permanent_deleted', 'permanent_deleted_at',
            'permanent_deleted_by', 'permanent_deleted_by_name',
            'is_protected', 'protection_reasons',
        ]


class DatabaseBackupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    formatted_size = serializers.SerializerMethodField()

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return "System / Scheduled"
        return obj.created_by.get_full_name() or obj.created_by.username

    def get_formatted_size(self, obj):
        bytes_val = obj.size_bytes
        if not bytes_val:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} TB"

    class Meta:
        model = DatabaseBackup
        fields = [
            'id', 'name', 'backup_type', 'status', 'size_bytes',
            'formatted_size', 'checksum_sha256', 'record_counts',
            'schema_version', 'db_engine', 'created_by', 'created_by_name',
            'created_at', 'verified_at', 'verification_message',
            'storage_backend', 'storage_key', 'r2_uploaded', 'r2_verified',
            'r2_etag', 'retention_until', 'is_protected', 'completed_at',
            'restore_status', 'error_message',
        ]
