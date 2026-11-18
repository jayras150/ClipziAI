# Global Agent Rules & Guidelines

1. **Communication Language:** Always communicate, explain, and respond to the user strictly in **Indonesian (Bahasa Indonesia)**, even when analyzing English code or error logs.
2. **Fast Execution & Minimal Delay:** Execute terminal/PowerShell commands efficiently with minimal sleep or wait intervals. Do not leave the user waiting unnecessarily; prefer fast, non-blocking execution whenever possible.
3. **Strict Git Push Guardrail:** You are **strictly prohibited** from pushing to any GitHub repository (or triggering any CI/CD / GitHub Actions workflows) until **all `@problems` (linter, compiler, and runtime errors/warnings) are completely resolved (zero `@problems`)**.
4. **Strict Docker Build Guardrail:** You are **strictly prohibited** from building any Docker images prematurely. Only build a Docker image once the entire task is 100% complete and there are **zero `@problems`**.
5. **Clear Decision Options:** Whenever you present options or choices that require the user's decision, you must clearly explain each option—including what it does, its pros/cons, and its impact—so the user can make an informed choice easily.