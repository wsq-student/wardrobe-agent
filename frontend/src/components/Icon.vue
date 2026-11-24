<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
const paths: Record<string,string> = {
  closet: 'M4 4h16v16H4z M12 4v16 M9 10v4 M15 10v4',
  sparkles: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z M20 2v4 M18 4h4',
  image: 'M4 4h16v16H4z M4 16l5-5 4 4 3-3 4 4 M15 8h.01',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2',
  search: 'M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0 M15 15l6 6',
  plus: 'M12 5v14 M5 12h14', back: 'M20 12H4 M11 5l-7 7 7 7',
  close: 'm6 6 12 12 M6 18 18 6', clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
  refresh: 'M20 8a9 9 0 0 0-15-3L3 8 M3 3v5h5 M4 16a9 9 0 0 0 15 3l2-3 M16 16h5v5',
  check: 'm5 12 4 4L19 6', expand: 'M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5',
  arrow: 'M12 19V5 M6 11l6-6 6 6', exit: 'M9 5H4v14h5 M10 12h11 M16 7l5 5-5 5',
}
</script>
<template><svg :width="size || 20" :height="size || 20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.sparkles"/></svg></template>
