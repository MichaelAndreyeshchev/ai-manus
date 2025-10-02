<template>
  <span class="inline-block text-[var(--text-primary)] font-bold select-none">LADS</span>
</template>

<script setup lang="ts">
// Preserve prop API so callers remain compatible
defineProps({
  width: { type: [String, Number], default: 88 },
  height: { type: [String, Number], default: 38 }
})
</script>