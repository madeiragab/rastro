import type { CapacitorConfig } from "@capacitor/cli";

/**
 * App Android do Rastro. Dois jeitos de gerar o APK:
 *
 * 1. **Produção** (padrão): o frontend vai EMBUTIDO no APK (pasta dist/) e fala
 *    com a API pelo endereço completo de `VITE_API_URL`. Exige login pelo
 *    Firebase (`VITE_FIREBASE_*` no build e `AUTH_MODO=firebase` na API),
 *    porque o app roda em https://localhost e cookie de sessão não atravessa
 *    origens. A API precisa ter https://localhost em CORS_ORIGINS.
 *
 * 2. **Desenvolvimento** (`RASTRO_DEV_URL=http://192.168.0.10:5173`): o APK
 *    abre o servidor de desenvolvimento da sua máquina pela rede local. Mesma
 *    origem, então o login local funciona sem Firebase. Bom para testar no
 *    celular; inútil fora do seu Wi-Fi.
 *
 * `appId` é o nome do pacote Android: é ele que você registra no console do
 * Firebase. Trocar depois exige baixar outro google-services.json.
 */
const urlDev = process.env.RASTRO_DEV_URL;

const config: CapacitorConfig = {
  appId: "com.madeiragab.rastro",
  appName: "Rastro",
  webDir: "dist",
  backgroundColor: "#0F1417",
  server: {
    androidScheme: "https",
    ...(urlDev ? { url: urlDev, cleartext: urlDev.startsWith("http://") } : {}),
  },
  plugins: {
    FirebaseMessaging: {
      // Com o app aberto, o Android não mostra a notificação sozinho; aqui
      // pedimos que mostre — o produtor pode estar olhando outra aba do app.
      presentationOptions: ["alert", "sound"],
    },
  },
};

export default config;
