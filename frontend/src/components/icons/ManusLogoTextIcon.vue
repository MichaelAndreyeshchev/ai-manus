<template>
  <div class="flex items-center gap-2">
    <img :width="width" :height="height" src="/lads-logo.png" alt="LADS" />
    <span class="font-semibold text-[var(--text-primary)]" :style="{ fontSize: textSize + 'px' }">LADS</span>
  </div>
</template>
<script setup lang="ts">
// Define props with default values
defineProps({
  width: {
    type: [String, Number],
    default: 88
  },
  height: {
    type: [String, Number],
    default: 38
  },
  textSize: {
    type: Number,
    default: 18
  }
})
</script>