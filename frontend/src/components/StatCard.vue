<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  caption: string
}>()
</script>

<template>
  <article class="stat-card">
    <h3>{{ label }}</h3>
    <div class="stat-value">{{ value }}</div>
    <div class="stat-caption">{{ caption }}</div>
  </article>
</template>

