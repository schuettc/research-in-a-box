import "./styles.css";
import "virtual:brand.css";
import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { AppRoutes } from "./App";
import { ShownContext } from "./routes/Dataset";

/**
 * Mount the app into `#app`. On a static dataset page, `#app` already holds the readable page:
 * the app renders aside and takes its place only once it has the dataset, so with no API the
 * static content stays.
 */
export function mount(app: HTMLElement): Root {
  const target = app.childElementCount > 0 ? document.createElement("div") : app;
  const shown = () => {
    if (target !== app && target.parentNode !== app) app.replaceChildren(target);
  };
  const root = createRoot(target);
  root.render(
    <StrictMode>
      <ShownContext value={shown}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ShownContext>
    </StrictMode>,
  );
  return root;
}

const app = document.getElementById("app");
if (app) mount(app);
