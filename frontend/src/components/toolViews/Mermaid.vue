<template>
  <div class="mermaid-container">
    <pre ref="el" class="mermaid">{{ code }}</pre>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUpdated, ref, watch, nextTick } from 'vue';

const props = defineProps<{ code: string }>();
const el = ref<HTMLElement | null>(null);

async function render() {
  await nextTick();
  if (!el.value) return;
  // lazy load mermaid to avoid bundling issues
  const mermaid = (await import('mermaid')).default;
  mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'default' });
  try {
    await mermaid.run({ querySelector: '.mermaid' });
  } catch (e) {
    // ignore render errors; show raw code
  }
}

onMounted(render);
onUpdated(render);
watch(() => props.code, render);
</script>

<style scoped>
.mermaid-container {
  overflow-x: auto;
}
.mermaid {
  white-space: pre-wrap;
}
</style>

