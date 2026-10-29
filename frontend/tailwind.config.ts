import type { Config } from "tailwindcss";
const config: Config = { content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"], theme: { extend: { colors: { ink: "#172321", muted: "#76817e", canvas: "#f5f7f4", brand: "#167c66", line: "#e4e9e5" }, boxShadow: { card: "0 8px 30px rgba(23,35,33,.05)" } } }, plugins: [] };
export default config;
