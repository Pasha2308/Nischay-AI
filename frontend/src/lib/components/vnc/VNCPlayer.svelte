<script lang="ts">
  // VNC is intentionally disabled for the working API demo.
  // This component remains as a placeholder so imports won't break if
  // re-enabled later, but it does not attempt any websocket connection.
  let { sessionUrl, password } = $props<{ sessionUrl: string; password: string }>();
</script>

<div class="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-800">
  <div class="font-medium">VNC disabled</div>
  <div class="mt-1 text-xs opacity-80">
    Session URL: {sessionUrl || '(none)'} • Password: {password ? '***' : '(none)'}
  </div>
</div>