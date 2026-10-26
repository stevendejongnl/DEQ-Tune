// The backend owns the USB link to the DEQ unit, so the app has no browser
// requirement of its own and mounts everywhere.
import "./components/app-root.ts";
import { displayController } from "./display/display-controller.ts";

// Before the first render, so the page does not flash dark before it goes
// light. Lit renders in a microtask, after this module body.
displayController.start();
