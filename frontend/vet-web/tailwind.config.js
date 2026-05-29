/** @type {import('tailwindcss').Config} */
export default {
    content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
    theme: {
        extend: {
            colors: {
                brand: {
                    600: "#2563eb",
                    700: "#1a6de8",
                },
            },
        },
    },
    plugins: [],
};
