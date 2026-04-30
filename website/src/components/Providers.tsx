import { FineIcon } from "@/ui/FineIcon";

type Provider = { name: string; prefix: string; key: string; default?: boolean };

const apiKeyProviders: Provider[] = [
  { name: "Google Gemini", prefix: "gemini/…", key: "GEMINI_API_KEY", default: true },
  { name: "OpenAI", prefix: "openai/…", key: "OPENAI_API_KEY" },
  { name: "Anthropic", prefix: "anthropic/…", key: "ANTHROPIC_API_KEY" },
  { name: "Groq", prefix: "groq/…", key: "GROQ_API_KEY" },
  { name: "Mistral", prefix: "mistral/…", key: "MISTRAL_API_KEY" },
  { name: "DeepSeek", prefix: "deepseek/…", key: "DEEPSEEK_API_KEY" },
  { name: "xAI Grok", prefix: "xai/…", key: "XAI_API_KEY" },
  { name: "Cohere", prefix: "cohere/…", key: "COHERE_API_KEY" },
  { name: "Perplexity", prefix: "perplexity/…", key: "PERPLEXITYAI_API_KEY" },
  { name: "OpenRouter", prefix: "openrouter/…", key: "OPENROUTER_API_KEY" },
  { name: "Together AI", prefix: "together_ai/…", key: "TOGETHERAI_API_KEY" },
  { name: "Fireworks", prefix: "fireworks_ai/…", key: "FIREWORKS_AI_API_KEY" },
  { name: "Cloudflare", prefix: "cloudflare/…", key: "CLOUDFLARE_API_KEY" },
  { name: "Azure OpenAI", prefix: "azure/…", key: "AZURE_API_KEY" },
  { name: "AWS Bedrock", prefix: "bedrock/…", key: "AWS_ACCESS_KEY_ID" },
];

const oauthProviders = [
  { name: "ChatGPT (OAuth)", model: "chatgpt/gpt-5.2", cmd: "notewise auth login chatgpt" },
  {
    name: "GitHub Copilot (OAuth)",
    model: "github_copilot/gpt-5-mini",
    cmd: "notewise auth login github_copilot",
  },
];

export function Providers() {
  return (
    <section
      id="providers"
      className="relative border-t border-[var(--rule)] bg-background py-20 sm:py-28 md:py-36"
    >
      <div className="mx-auto max-w-[1200px] px-5 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[1fr_1.5fr] md:gap-16 lg:gap-20">
          <div>
            <>
              <span className="t-eyebrow">No 04 · Providers</span>
            </>
            <>
              <h2 className="mt-3 t-h2">
                Bring the model
                <br />
                you <em className="text-stamp">already pay</em> for.
              </h2>
            </>
            <>
              <p className="mt-5 max-w-md t-body">
                NoteWise routes through{" "}
                <a
                  className="underline-ink"
                  href="https://github.com/BerriAI/litellm"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  LiteLLM
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
                . Set one environment variable, hand it any supported model string, and you're done.
                Default is Gemini 2.5 Flash — its free tier comfortably covers a full course.
              </p>
            </>
            <>
              <p className="mt-5 t-mono-meta">
                ¶ Any LiteLLM-supported model string works — including local llama.cpp endpoints.
              </p>
            </>
          </div>

          <div className="space-y-6">
            {/* ── Desktop table ─────────────────────────────────────────── */}
            <>
              <div className="hidden md:block overflow-hidden rounded-lg border border-[var(--rule)]">
                <table className="w-full table-fixed">
                  <thead>
                    <tr className="grid grid-cols-[1.1fr_1.2fr_1fr] bg-muted px-5 py-2.5 t-mono-meta uppercase tracking-[0.18em]">
                      <th scope="col" className="text-left font-inherit">
                        Provider
                      </th>
                      <th scope="col" className="text-left font-inherit">
                        Model prefix
                      </th>
                      <th scope="col" className="text-right font-inherit">
                        Env key
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {apiKeyProviders.map((p) => (
                      <tr
                        key={p.name}
                        className="grid grid-cols-[1.1fr_1.2fr_1fr] items-center gap-3 border-t border-[var(--rule)] bg-card px-5 py-3"
                      >
                        <td className="flex items-center gap-2 min-w-0">
                          <span className="font-display text-[17px] truncate">{p.name}</span>
                          {p.default && (
                            <span className="rounded-full border border-stamp/40 px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.18em] text-stamp">
                              default
                            </span>
                          )}
                        </td>
                        <td className="min-w-0">
                          <code className="block truncate t-code text-foreground/85">
                            {p.prefix}
                          </code>
                        </td>
                        <td className="min-w-0 text-right">
                          <code className="block truncate t-mono-meta">{p.key}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>

            {/* ── Mobile stacked cards ─────────────────────────────────── */}
            <div className="md:hidden grid grid-cols-1 sm:grid-cols-2 gap-3">
              {apiKeyProviders.map((p) => (
                <div key={p.name} className="leaf-card p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-display text-[17px]">{p.name}</span>
                    {p.default && (
                      <span className="rounded-full border border-stamp/40 px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.18em] text-stamp">
                        default
                      </span>
                    )}
                  </div>
                  <code className="mt-2 block t-code text-foreground/85 truncate">{p.prefix}</code>
                  <code className="mt-1 block t-mono-meta truncate">{p.key}</code>
                </div>
              ))}
            </div>

            {/* ── OAuth providers ──────────────────────────────────────── */}
            <>
              <div className="rounded-lg border border-[var(--rule)] overflow-hidden">
                <div className="flex items-center gap-2 bg-muted px-5 py-2.5">
                  <FineIcon name="key" size={12} className="text-stamp" />
                  <span className="t-mono-meta uppercase tracking-[0.18em]">
                    OAuth · no API key needed
                  </span>
                </div>
                <ul>
                  {oauthProviders.map((p) => (
                    <li
                      key={p.name}
                      className="grid grid-cols-1 sm:grid-cols-[1fr_1.2fr_auto] items-start sm:items-center gap-2 sm:gap-4 border-t border-[var(--rule)] bg-card px-5 py-3.5"
                    >
                      <span className="font-display text-[16.5px]">{p.name}</span>
                      <code className="t-code text-foreground/85 truncate">{p.model}</code>
                      <code className="t-mono-meta text-stamp truncate sm:text-right">{p.cmd}</code>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          </div>
        </div>
      </div>
    </section>
  );
}
