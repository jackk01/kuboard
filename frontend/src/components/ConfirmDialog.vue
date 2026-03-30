<script setup lang="ts">
defineProps<{
  visible: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="dialog-overlay" @click.self="emit('cancel')">
        <div class="dialog-card">
          <h3 class="dialog-title">{{ title || '确认操作' }}</h3>
          <p class="dialog-message">{{ message }}</p>
          <div class="dialog-actions">
            <button class="button button-secondary" @click="emit('cancel')">
              {{ cancelText || '取消' }}
            </button>
            <button
              :class="['button', danger ? 'button-danger' : 'button-primary']"
              @click="emit('confirm')"
            >
              {{ confirmText || '确认' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(4px);
}

.dialog-card {
  width: min(440px, calc(100vw - 48px));
  padding: 28px;
  border-radius: 0;
  background: var(--kb-surface-strong, #ffffff);
  box-shadow: 0 24px 64px rgba(16, 32, 51, 0.18);
}

.dialog-title {
  margin: 0 0 12px;
  font-size: 18px;
}

.dialog-message {
  margin: 0 0 24px;
  color: var(--kb-text-soft, #5a6b7d);
  font-size: 14px;
  line-height: 1.6;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 200ms ease;
}

.dialog-fade-enter-active .dialog-card,
.dialog-fade-leave-active .dialog-card {
  transition: transform 200ms ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-from .dialog-card {
  transform: scale(0.95) translateY(8px);
}

.dialog-fade-leave-to .dialog-card {
  transform: scale(0.95) translateY(8px);
}
</style>
