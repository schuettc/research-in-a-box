import "./styles.css";
import { mount } from "./App";

const app = document.getElementById("app");
if (!app) throw new Error("missing #app element");
mount(app);
