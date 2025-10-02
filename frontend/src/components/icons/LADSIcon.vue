<template>
  <span class="inline-block text-[var(--text-primary)] font-bold select-none">LADS</span>
</template>

<script setup lang="ts">
// Keep width/height props for API compatibility, though unused by text
defineProps({
  width: { type: [String, Number], default: 88 },
  height: { type: [String, Number], default: 38 }
})
</script>

