import { useEffect, useMemo, useRef, useState } from "react";
import {
  AtSign, Bot, ChevronDown, Clock3, Command, ExternalLink, FolderOpen,
  Github, Grid2X2, Link2, Menu, MessageCircle, Mic, Moon, Paperclip,
  Search, Send, Settings2, SlidersHorizontal, Sparkles, TerminalSquare,
  UserRound, X, Youtube, MonitorCog, Palette, Info, Check, Zap, Eye, EyeOff
} from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { getCoreStatus, getLLMConfig, getLLMModels, isConfigRequestError, isCoreUnavailableError, saveLLMKey, selectLLMModel, sendToCore, testLLMConnection, type CoreRuntimeStatus, type LLMConfigStatus } from "./services/yusanClient";

type Page = "chat" | "commands" | "library" | "settings";
type Role = "assistant" | "user";
type Message = { id: number; role: Role; text: string; time: string; card?: boolean };
type StartupState = "INITIALIZING" | "STARTING_CORE" | "WAITING_FOR_CORE" | "CORE_READY" | "READY" | "ERROR";

const STARTUP_POLL_INTERVAL_MS = 250;
const STARTUP_TIMEOUT_MS = 20_000;

const commands = [
  { label: "Safari'yi aç", icon: <ExternalLink size={18} />, prompt: "Safari'yi aç" },
  { label: "YouTube'u aç", icon: <Youtube size={18} />, prompt: "YouTube'u aç" },
  { label: "Google'da ara", icon: <Search size={18} />, prompt: "Google'da YUSAN ara" },
  { label: "Saat kaç?", icon: <Clock3 size={18} />, prompt: "Saat kaç?" },
  { label: "Sistemi uyut", icon: <Moon size={18} />, prompt: "Sistemi uyut" },
  { label: "Ayarları aç", icon: <Settings2 size={18} />, prompt: "Ayarları aç" }
];

const initialMessages: Message[] = [
  { id: 1, role: "user", text: "Selam Yusan.", time: "23:14" },
  { id: 2, role: "assistant", text: "Selam! 👋\nBen Yusan.\nNasıl yardımcı olabilirim?", time: "23:14" },
  { id: 3, role: "user", text: "Bugünkü NBA sonuçlarını ara.", time: "23:15" },
  { id: 4, role: "assistant", text: "Tabii, bugünkü NBA sonuçlarını senin için arıyorum...", time: "23:15", card: true }
];

function RingLogo({ small = false }: { small?: boolean }) {
  return <span className={`ring-logo ${small ? "ring-logo--small" : ""}`} aria-label="YUSAN" />;
}

function NativeTitlebarDragRegion() {
  const zoomWindow = () => {
    void getCurrentWindow().toggleMaximize().catch(() => undefined);
  };

  return <div
    className="native-titlebar-drag-region"
    data-tauri-drag-region
    onDoubleClick={zoomWindow}
    aria-label="Pencere başlık çubuğu"
  />;
}

function AssistantBubble({ message }: { message: Message }) {
  return (
    <div className="assistant-row">
      <RingLogo small />
      <article className="message message--assistant">
        <p>{message.text}</p>
        {message.card && <div className="result-card">
          <div className="nba-mark">NBA</div>
          <div><strong>Bugünkü NBA Sonuçları</strong><span>En güncel NBA maç sonuçlarını tarayıcıda açıyorum.</span></div>
          <button><ExternalLink size={15} /> Tarayıcıda Aç</button>
        </div>}
        <time>{message.time}</time>
      </article>
    </div>
  );
}

function UserBubble({ message }: { message: Message }) {
  return <div className="user-row">
    <article className="message message--user"><p>{message.text}</p><time>{message.time}</time></article>
    <div className="user-avatar"><UserRound size={23} fill="currentColor" /></div>
  </div>;
}

function Sidebar({ active, onSelect }: { active: Page; onSelect: (page: Page) => void }) {
  const items: { id: Page; label: string; icon: React.ReactNode }[] = [
    { id: "chat", label: "Chat", icon: <MessageCircle /> },
    { id: "commands", label: "Commands", icon: <TerminalSquare /> },
    { id: "library", label: "Library", icon: <Grid2X2 /> },
    { id: "settings", label: "Settings", icon: <Settings2 /> }
  ];
  return <aside className="sidebar">
    <div className="brand"><RingLogo small /><span>YUSAN</span></div>
    <nav>{items.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onSelect(item.id)}>{item.icon}<span>{item.label}</span></button>)}</nav>
    <div className="sidebar-footer"><RingLogo small /><div><b>YUSAN <em>v1.0</em></b><small>Your Assistant</small></div></div>
  </aside>;
}

function ChatScreen({ messages, value, setValue, onSend, coreStatus }: { messages: Message[]; value: string; setValue: (value: string) => void; onSend: (text?: string) => void; coreStatus: CoreRuntimeStatus }) {
  const conversationRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const conversation = conversationRef.current;
    if (conversation) conversation.scrollTo({ top: conversation.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  const coreLabel = coreStatus.state === "online" ? "Online" : coreStatus.state === "starting" ? "YUSAN Core başlatılıyor..." : "Core çevrimdışı";

  return <main className="content chat-content">
    <header className="topbar"><div /><div className="topbar-actions"><span className="online"><i /> {coreLabel}</span><button aria-label="Ara"><Search size={21} /></button></div></header>
    <section className="conversation" ref={conversationRef}>
      {messages.map(message => message.role === "assistant" ? <AssistantBubble key={message.id} message={message} /> : <UserBubble key={message.id} message={message} />)}
    </section>
    <form className="composer" onSubmit={event => { event.preventDefault(); onSend(); }}>
      <button type="button" aria-label="Dosya ekle"><Paperclip /></button>
      <input value={value} onChange={event => setValue(event.target.value)} placeholder="Yusan'a bir şey sor..." />
      <button className="send" type="submit" aria-label="Gönder"><Send size={22} /></button>
    </form>
  </main>;
}

function CommandPalette({ open, onClose, onRun }: { open: boolean; onClose: () => void; onRun: (prompt: string) => void }) {
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => commands.filter(command => command.label.toLocaleLowerCase("tr").includes(filter.toLocaleLowerCase("tr"))), [filter]);
  useEffect(() => { if (!open) setFilter(""); }, [open]);
  if (!open) return null;
  return <div className="palette-scrim" onMouseDown={onClose}>
    <section className="command-palette" onMouseDown={event => event.stopPropagation()}>
      <div className="palette-search"><Search size={20} /><input autoFocus value={filter} onChange={event => setFilter(event.target.value)} placeholder="Yusan'a komut ver..." /><kbd>⌘ K</kbd></div>
      <div className="palette-list">{shown.map((command, index) => <button key={command.label} className={index === 0 ? "selected" : ""} onClick={() => { onRun(command.prompt); onClose(); }}><span>{command.icon}</span>{command.label}</button>)}</div>
      <footer><span><ChevronDown size={14} /> gezinin</span><span><kbd>↵</kbd> seçin</span><span><kbd>esc</kbd> kapatın</span></footer>
    </section>
  </div>;
}

function CommandsScreen({ onRun }: { onRun: (prompt: string) => void }) {
  return <main className="content showcase"><header className="page-heading"><span className="eyebrow">HIZLI KOMUTLAR</span><h1>Ne yapmak istersin?</h1><p>YUSAN, günlük işlerini tek bir cümleyle halletmene yardımcı olur.</p></header><div className="command-grid">{commands.map(command => <button key={command.label} onClick={() => onRun(command.prompt)}><span>{command.icon}</span><b>{command.label}</b><ChevronDown size={16} /></button>)}</div></main>;
}

function LibraryScreen() {
  return <main className="content showcase library"><header className="page-heading"><span className="eyebrow">KÜTÜPHANE</span><h1>Senin için saklananlar</h1><p>Konuşmaların, bağlantıların ve sık kullandığın komutlar burada görünecek.</p></header><div className="empty-state"><FolderOpen size={36} /><b>Henüz bir şey yok</b><span>YUSAN ile yaptığın keşifler burada kalacak.</span></div></main>;
}

const settingSections = [
  ["Genel", <Settings2 />], ["Görünüm", <MonitorCog />], ["Komutlar", <TerminalSquare />], ["Hesap", <UserRound />], ["Hakkında", <Info />]
];

const llmStatusText: Record<LLMConfigStatus["status"], string> = {
  configured: "API anahtarı kaydedildi",
  connected: "Bağlı",
  api_key_required: "API anahtarı gerekli",
  invalid_api_key: "Geçersiz API anahtarı",
  model_unavailable: "Model kullanılamıyor",
  permission_denied: "Model erişimi yok",
  quota_exceeded: "API kotası aşıldı",
  connection_failed: "Bağlantı başarısız",
  service_error: "Gemini hizmet hatası",
  unknown_error: "Gemini yanıt veremedi",
  invalid_provider: "Desteklenmeyen sağlayıcı"
};

const initialCoreStatus: CoreRuntimeStatus = { state: "starting", endpoint: "", message: "YUSAN Core başlatılıyor..." };

function SettingsScreen({ background, setBackground, coreStatus }: { background: boolean; setBackground: (value: boolean) => void; coreStatus: CoreRuntimeStatus }) {
  const [selected, setSelected] = useState("Genel");
  const [theme, setTheme] = useState("Otomatik");
  const [accent, setAccent] = useState("violet");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [llmStatus, setLLMStatus] = useState<LLMConfigStatus>({ configured: false, provider: "gemini", model: "", status: "api_key_required" });
  const [llmMessage, setLLMMessage] = useState("YUSAN Core başlatılıyor...");
  const [models, setModels] = useState<string[]>([]);
  const [modelLabel, setModelLabel] = useState("Core başlatılıyor...");

  const loadConfiguration = async () => {
    try {
      const status = await getLLMConfig();
      setLLMStatus(status);
      setLLMMessage(llmStatusText[status.status]);
      if (!status.configured) {
        setModels([]);
        setModelLabel("API anahtarı gerekli");
        return;
      }
      setModelLabel("Modeller yükleniyor...");
      const available = await getLLMModels();
      setLLMStatus(current => ({ ...current, provider: available.provider, model: available.selected_model ?? current.model, status: available.status }));
      if (available.models.length) {
        setModels(available.models);
        setModelLabel(available.selected_model ?? available.models[0]);
      } else {
        setModels([]);
        setModelLabel(available.message ?? "Model yüklenemedi");
        setLLMMessage(available.message ?? llmStatusText[available.status]);
      }
    } catch (error) {
      setModels([]);
      if (isCoreUnavailableError(error)) {
        setLLMMessage(error.status.message);
        setModelLabel(error.status.state === "starting" ? "Core başlatılıyor..." : "Model yüklenemedi");
      } else {
        setLLMMessage("YUSAN Core'a bağlanılamadı");
        setModelLabel("Model yüklenemedi");
      }
    }
  };

  useEffect(() => {
    if (coreStatus.state === "starting") {
      setModels([]); setLLMMessage("YUSAN Core başlatılıyor..."); setModelLabel("Core başlatılıyor..."); return;
    }
    if (coreStatus.state !== "online") {
      setModels([]); setLLMMessage(coreStatus.message); setModelLabel("Model yüklenemedi"); return;
    }
    void loadConfiguration();
  }, [coreStatus.state, coreStatus.endpoint]);

  const saveKey = async () => {
    if (!apiKey.trim()) { setLLMStatus(current => ({ ...current, status: "api_key_required" })); setLLMMessage("API anahtarı gerekli"); return; }
    console.info("[YUSAN credential] Settings save requested", { provider: "gemini", apiKeyReceived: true, apiKeyLength: apiKey.length });
    setBusy("save");
    try {
      const status = await saveLLMKey("gemini", apiKey);
      setApiKey("");
      setShowApiKey(false);
      setLLMStatus(status);
      setLLMMessage("API anahtarı güvenli şekilde kaydedildi");
      void loadConfiguration();
    } catch (error) {
      setLLMStatus(current => ({ ...current, status: "connection_failed" }));
      setLLMMessage(isConfigRequestError(error) ? error.detail.message : "YUSAN Core'a bağlanılamadı");
    } finally { setBusy(null); }
  };

  const changeModel = async (model: string) => {
    setBusy("save");
    try {
      const status = await selectLLMModel("gemini", model);
      setLLMStatus(status);
      setModelLabel(status.model);
      setLLMMessage("Model seçildi");
    } catch (error) {
      setLLMMessage(isConfigRequestError(error) ? error.detail.message : "Model yüklenemedi");
    } finally { setBusy(null); }
  };

  const testConnection = async () => {
    setBusy("test");
    try {
      const result = await testLLMConnection("gemini");
      const status: LLMConfigStatus = { configured: result.success || llmStatus.configured, provider: result.provider, model: result.model ?? llmStatus.model, status: result.status };
      setLLMStatus(status);
      setLLMMessage(result.success ? "Bağlı" : result.message ?? llmStatusText[result.status]);
    } catch {
      setLLMStatus(current => ({ ...current, status: "connection_failed" }));
      setLLMMessage("Bağlantı başarısız");
    } finally { setBusy(null); }
  };

  return <main className="content settings-content"><header className="settings-title"><RingLogo small /><h1>Ayarlar</h1></header><div className="settings-layout"><aside className="settings-nav">{settingSections.map(([name, icon]) => <button className={selected === name ? "active" : ""} key={String(name)} onClick={() => setSelected(String(name))}>{icon as React.ReactNode}<span>{name}</span></button>)}</aside><section className="preferences"><h2>{selected}</h2><div className="preference-card"><label>Tema</label><div className="theme-row">{["Otomatik", "Koyu", "Açık"].map(name => <button key={name} onClick={() => setTheme(name)} className={`theme-choice ${theme === name ? "picked" : ""}`}><i /><span>{name}</span>{theme === name && <Check size={14} />}</button>)}</div></div><div className="preference-card"><div className="row-label"><div><label>Arka plan efekti</label><span>Yumuşak ışık ve cam derinliği</span></div><button className={`toggle ${background ? "on" : ""}`} onClick={() => setBackground(!background)}><i /></button></div></div><div className="preference-card"><div className="row-label"><label>Şeffaflık</label><span>%70</span></div><input aria-label="Şeffaflık" className="range" type="range" min="20" max="100" defaultValue="70" /></div><div className="preference-card"><label>Vurgu rengi</label><div className="accent-row">{["violet", "blue", "pink", "amber", "green"].map(color => <button key={color} className={`${color} ${accent === color ? "chosen" : ""}`} onClick={() => setAccent(color)} aria-label={color} />)}</div></div><div className="preference-card llm-card"><div className="row-label"><div><label>Yapay zekâ</label><span>YUSAN Core üzerinden güvenli bağlantı</span></div><span className={`llm-status llm-status--${llmStatus.status}`}>{llmStatusText[llmStatus.status]}</span></div><label className="llm-field-label" htmlFor="llm-provider">Sağlayıcı</label><select id="llm-provider" className="provider-select" value="gemini" disabled><option value="gemini">Gemini</option></select><label className="llm-field-label" htmlFor="llm-model">Model</label>{models.length ? <select id="llm-model" className="model-display" value={modelLabel} disabled={busy !== null} onChange={event => void changeModel(event.target.value)}>{models.map(model => <option key={model} value={model}>{model}</option>)}</select> : <div className="model-display">{modelLabel}</div>}<label className="llm-field-label" htmlFor="gemini-api-key">API anahtarı</label><div className="api-key-input"><input id="gemini-api-key" value={apiKey} onChange={event => setApiKey(event.target.value)} type={showApiKey ? "text" : "password"} autoComplete="off" spellCheck="false" placeholder="Gemini API anahtarını gir" /><button type="button" onClick={() => setShowApiKey(value => !value)} aria-label={showApiKey ? "API anahtarını gizle" : "API anahtarını göster"}>{showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div><div className="llm-actions"><button className="secondary-action" type="button" disabled={busy !== null || coreStatus.state !== "online"} onClick={() => void testConnection()}>{busy === "test" ? "Test ediliyor..." : "Bağlantıyı Test Et"}</button><button className="primary-action" type="button" disabled={busy !== null || coreStatus.state !== "online"} onClick={() => void saveKey()}>{busy === "save" ? "Kaydediliyor..." : "Kaydet"}</button></div><p className="llm-message">{llmMessage}</p></div></section></div></main>;
}

function Startup({ state, message, onRetry }: { state: StartupState; message: string; onRetry: () => void }) {
  const failed = state === "ERROR";
  return <div className="startup" role="status" aria-live="polite"><div className="startup-landscape" /><div className="startup-center"><RingLogo /><strong>YUSAN</strong><div className="loading-track"><i /></div><span>{failed ? message : "Başlatılıyor..."}</span>{failed && <button className="startup-retry" type="button" onClick={onRetry}>Tekrar Dene</button>}</div></div>;
}

export default function App() {
  const [page, setPage] = useState<Page>("chat");
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [background, setBackground] = useState(true);
  const [coreStatus, setCoreStatus] = useState<CoreRuntimeStatus>(initialCoreStatus);
  const [startupState, setStartupState] = useState<StartupState>("INITIALIZING");
  const [startupAttempt, setStartupAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    let pollTimer: number | undefined;
    let timeoutTimer: number | undefined;

    const transition = (next: StartupState) => {
      setStartupState(current => {
        if (current !== next) console.info(`[Startup] ${current} -> ${next}`);
        return next;
      });
    };

    const fail = (message: string) => {
      if (!active) return;
      console.info("[Startup] Core readiness failed", { message });
      setCoreStatus(current => ({ ...current, state: "error", message }));
      transition("ERROR");
    };

    const poll = async () => {
      try {
        const status = await getCoreStatus();
        if (!active) return;
        setCoreStatus(status);

        if (status.state === "online") {
          window.clearTimeout(timeoutTimer);
          console.info("[Startup] /health ready", { endpoint: status.endpoint });
          transition("CORE_READY");
          transition("READY");
          return;
        }

        if (status.state === "error" || status.state === "offline") {
          fail(status.message || "YUSAN Core başlatılamadı");
          return;
        }
      } catch {
        // The Tauri bridge can come online after the webview; keep retrying within the startup bound.
        if (!active) return;
        console.info("[Startup] Core status unavailable; retrying");
      }

      if (active) pollTimer = window.setTimeout(() => void poll(), STARTUP_POLL_INTERVAL_MS);
    };

    console.info("[Startup] INITIALIZING");
    transition("STARTING_CORE");
    transition("WAITING_FOR_CORE");
    timeoutTimer = window.setTimeout(() => fail("YUSAN Core başlatılamadı"), STARTUP_TIMEOUT_MS);
    void poll();

    return () => {
      active = false;
      window.clearTimeout(pollTimer);
      window.clearTimeout(timeoutTimer);
    };
  }, [startupAttempt]);

  useEffect(() => {
    if (startupState !== "READY") return;
    let active = true;
    const refresh = () => {
      void getCoreStatus()
        .then(status => { if (active) setCoreStatus(status); })
        .catch(() => { if (active) setCoreStatus(current => ({ ...current, state: "error", message: "YUSAN Core'a bağlanılamadı" })); });
    };
    refresh();
    const interval = window.setInterval(refresh, 2_000);
    return () => { active = false; window.clearInterval(interval); };
  }, [startupState]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPaletteOpen(true); } if (event.key === "Escape") setPaletteOpen(false); };
    window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler);
  }, []);

  const send = async (command?: string) => {
    const text = (command ?? draft).trim();
    if (!text) return;
    const timestamp = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" }).format(new Date());
    setMessages(current => [...current, { id: Date.now(), role: "user", text, time: timestamp }]);
    setDraft(""); setPage("chat");
    if (text.includes("Ayarları aç")) { setPage("settings"); setMessages(current => [...current, { id: Date.now() + 1, role: "assistant", text: "Ayarlar sayfasını açıyorum.", time: timestamp }]); return; }
    try {
      const response = await sendToCore(text);
      setMessages(current => [...current, { id: Date.now() + 1, role: "assistant", text: response.content ?? response.message ?? "Üzgünüm, bir yanıt oluşturamadım.", time: timestamp }]);
    } catch {
      setMessages(current => [...current, { id: Date.now() + 1, role: "assistant", text: "YUSAN Core şu an çevrimdışı. Core'u başlattığında isteklerini burada yanıtlayacağım.", time: timestamp }]);
    }
  };

  return <div className={`app-shell ${background ? "effects-on" : "effects-off"}`}>
    {startupState !== "READY" && <Startup state={startupState} message={coreStatus.message || "YUSAN Core başlatılamadı"} onRetry={() => setStartupAttempt(current => current + 1)} />}
    <div className="aurora aurora-one" /><div className="aurora aurora-two" />
    <div className="app-window"><NativeTitlebarDragRegion /><Sidebar active={page} onSelect={setPage} />{page === "chat" && <ChatScreen messages={messages} value={draft} setValue={setDraft} onSend={send} coreStatus={coreStatus} />}{page === "commands" && <CommandsScreen onRun={send} />}{page === "library" && <LibraryScreen />}{page === "settings" && <SettingsScreen background={background} setBackground={setBackground} coreStatus={coreStatus} />}</div>
    <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onRun={send} />
  </div>;
}
