export async function copyText(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  const previouslyFocused =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  try {
    textarea.select();
    if (!document.execCommand("copy")) {
      throw new Error("Copy was rejected");
    }
  } finally {
    textarea.remove();
    try {
      if (previouslyFocused?.isConnected) {
        previouslyFocused.focus({ preventScroll: true });
      }
    } catch {
      // Ignore focus restoration failures; the copy attempt has already completed.
    }
  }
}
