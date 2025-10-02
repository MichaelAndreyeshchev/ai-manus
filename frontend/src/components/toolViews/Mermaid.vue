<template>
  <div class="mermaid-container">
    <div ref="viewport" class="mermaid-viewport">
      <pre ref="el" class="mermaid">{{ code }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUpdated, ref, watch, nextTick, onBeforeUnmount } from 'vue';

const props = defineProps<{ code: string }>();
const el = ref<HTMLElement | null>(null);
const viewport = ref<HTMLElement | null>(null);
let panzoomInstance: any = null;

async function render() {
  await nextTick();
  if (!el.value) return;
  // lazy load mermaid to avoid bundling issues
  const mermaid = (await import('mermaid')).default;
  mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'default' });
  try {
    await mermaid.run({ querySelector: '.mermaid' });
    // Mount panzoom after render
    const panzoom = (await import('panzoom')).default;
    if (viewport.value && !panzoomInstance) {
      panzoomInstance = panzoom(viewport.value, { smoothScroll: false, bounds: true, maxZoom: 5, minZoom: 0.2 });
    }
  } catch (e) {
    // ignore render errors; show raw code
  }
}

onMounted(render);
onUpdated(render);
watch(() => props.code, render);
onBeforeUnmount(() => {
  if (panzoomInstance && panzoomInstance.dispose) panzoomInstance.dispose();
  panzoomInstance = null;
});
</script>

<style scoped>
.mermaid-container {
  overflow-x: auto;
}
.mermaid-viewport {
  width: 100%;
  height: 100%;
}
.mermaid {
  white-space: pre-wrap;
}
</style>

