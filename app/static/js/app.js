import "./app-modules.js";
import { createTesisAI } from "./features/app-shell.js";

const TesisAI = createTesisAI();

window.TesisAI = TesisAI;
window.addEventListener("DOMContentLoaded", () => {
  TesisAI.boot().catch(console.error);
});
