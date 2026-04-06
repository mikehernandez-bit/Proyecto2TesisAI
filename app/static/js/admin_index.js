document.addEventListener("DOMContentLoaded", () => {
  import("/static/js/features/prompt-packages/admin-list.js")
    .then(({ bootPromptPackageAdminList }) => {
      bootPromptPackageAdminList();
    })
    .catch((error) => {
      console.error("bootPromptPackageAdminList error:", error);
    });
});
