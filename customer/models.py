from django.db import models
from django.conf import settings


class ChatRoom(models.Model):
    """Комната чата — по одной на каждого пользователя."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_room')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'чат'
        verbose_name_plural = 'чаты'

    def __str__(self):
        return f"Чат: {self.user.get_full_name() or self.user.phone}"

    def unread_for_staff(self):
        return self.messages.filter(is_staff_message=False, is_read=False).count()

    def unread_for_user(self):
        return self.messages.filter(is_staff_message=True, is_read=False).count()


class ChatMessage(models.Model):
    """Сообщение в чате."""
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_staff_message = models.BooleanField(default=False)
    text = models.TextField('Сообщение')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'сообщение'
        verbose_name_plural = 'сообщения'

    def __str__(self):
        return f"{self.author}: {self.text[:50]}"
