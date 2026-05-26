<script lang="ts">
  import { ICONS } from '$lib/icons';
  export let name: string;
  export let size: number = 16;
  export let strokeWidth: number = 1.8;
</script>

<svg
  xmlns="http://www.w3.org/2000/svg"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={strokeWidth}
  stroke-linecap="round"
  stroke-linejoin="round"
  class="inline-block flex-shrink-0"
>
  {#each (ICONS[name] || '').split(' M').filter(Boolean) as d, i}
    <path d={(i === 0 ? '' : 'M') + d} />
  {/each}
</svg>
