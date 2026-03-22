<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: string
}>()

const className = computed(() => {
  const normalized = props.value.toLowerCase()
  return `status-badge status-${normalized}`
})
</script>

<template>
  <span :class="className">{{ value }}</span>
</template>

