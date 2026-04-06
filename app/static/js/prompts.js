document.addEventListener("DOMContentLoaded", () => {
  import("/static/js/features/prompt-packages/editor.js")
    .then(({ bootPromptPackageEditor }) => {
      bootPromptPackageEditor();
    })
    .catch((error) => {
      console.error("bootPromptPackageEditor error:", error);
    });
});
