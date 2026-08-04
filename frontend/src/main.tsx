import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// O CSS do Leaflet entra pelo bundle, não por CDN: o mapa é a tela principal e
// não pode depender do unpkg estar de pé. Antes do styles.css para que os
// nossos ajustes venham depois na cascata.
import "leaflet/dist/leaflet.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
