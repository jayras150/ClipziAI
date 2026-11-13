"use client";

import { useMemo, useRef, useState, useTransition } from "react";

import {
  clearProxies,
  fetchProxyPool,
  parseProxyText,
  saveProxies,
  startProxyFilter,
  toggleProxies,
  uploadProxyFiles,
  type ParseResult,
  type ProxyItem,
  type ProxyPoolView
} from "@/app/dashboard/settings/proxy-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ClipzySpinner } from "@/components/ui/clipzy-spinner";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type FilterStatus = {
  status: string;
  total: number;
  tested: number;
  active: number;
  dead: number;
  error?: string | null;
};

type Preview = ParseResult & { source?: "files" | "paste" };

export function ProxyManager({ initial }: { initial: ProxyPoolView }) {
  const [pool, setPool] = useState<ProxyPoolView>(initial);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mode, setMode] = useState<"files" | "paste">("files");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<FilterStatus | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, startTransition] = useTransition();
  const [filtering, setFiltering] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const activeItems = useMemo(
    () => (pool.items || []).filter((item) => item.status === "active"),
    [pool.items]
  );

  const pollStatus = async () => {
    for (let i = 0; i < 240; i += 1) {
      const response = await fetch("/api/proxies/status", { cache: "no-store" });
      const data = (await response.json()) as FilterStatus;
      setStatus(data);
      if (data.status !== "running") return data;
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    return null;
  };

  const onFiles = (files: FileList | null) => {
    if (!files || !files.length) return;
    setError("");
    setMessage("");
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("files", file));
    startTransition(async () => {
      try {
        const parsed = await uploadProxyFiles(formData);
        setPreview({ ...parsed, source: "files" });
        setMessage(parsed.valid + " proxy valid dari " + files.length + " file");
      } catch (err) {
        setError((err as Error).message);
      }
    });
  };

  const onParseText = () => {
    setError("");
    setMessage("");
    startTransition(async () => {
      try {
        const parsed = await parseProxyText(text);
        setPreview({ ...parsed, source: "paste" });
        setMessage(parsed.valid + " proxy valid, " + parsed.errors.length + " baris gagal");
      } catch (err) {
        setError((err as Error).message);
      }
    });
  };

  const onStartFilter = () => {
    setError("");
    setMessage("");
    setFiltering(true);
    startTransition(async () => {
      try {
        const result = await startProxyFilter({
          text: mode === "paste" ? text : undefined,
          items: preview?.source === "files" ? (preview.items as ProxyItem[]) : undefined,
          check_youtube: true
        });
        if (!result.started) {
          setError(result.message || "Filter tidak bisa dimulai");
          setFiltering(false);
          return;
        }
        const finalStatus = await pollStatus();
        const fresh = await fetchProxyPool();
        setPool(fresh);
        setFiltering(false);
        if (finalStatus) {
          setMessage(
            "Filter selesai: " + finalStatus.active + " aktif, " + finalStatus.dead + " mati dibuang"
          );
        }
      } catch (err) {
        setError((err as Error).message);
        setFiltering(false);
      }
    });
  };

  const onSaveOnly = () => {
    if (!preview?.items?.length) return;
    startTransition(async () => {
      try {
        const fresh = await saveProxies(preview.items as ProxyItem[]);
        setPool(fresh);
        setMessage("Daftar proxy disimpan (belum diuji). Jalankan START FILTER agar hanya yang aktif dipakai.");
      } catch (err) {
        setError((err as Error).message);
      }
    });
  };

  const onToggleAutoUse = () => {
    startTransition(async () => {
      const fresh = await toggleProxies({ auto_use: !pool.auto_use });
      setPool(fresh);
      setMessage(fresh.auto_use ? "Auto-use diaktifkan." : "Auto-use dimatikan (proxy tidak dipakai).");
    });
  };

  const onClear = () => {
    startTransition(async () => {
      const fresh = await clearProxies();
      setPool(fresh);
      setPreview(null);
      setMessage("Semua proxy dihapus.");
    });
  };

  const progress = status && status.total ? Math.round((status.tested / status.total) * 100) : 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <CardTitle>Proxy YouTube</CardTitle>
            <CardDescription>
              Urutan percobaan worker: <strong>cookies → tanpa cookies → proxy aktif</strong>. Hanya proxy
              berstatus aktif yang dipakai sistem (file <code>active.txt</code> dibuat otomatis).
            </CardDescription>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Badge variant={pool.auto_use ? "secondary" : "outline"}>
              {pool.auto_use ? "auto-use: aktif" : "auto-use: mati"}
            </Badge>
            <Badge variant="outline">{activeItems.length} proxy aktif</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant={mode === "files" ? "default" : "outline"} onClick={() => setMode("files")}>
              Upload file .txt
            </Button>
            <Button size="sm" variant={mode === "paste" ? "default" : "outline"} onClick={() => setMode("paste")}>
              Paste teks
            </Button>
            <Button size="sm" variant="outline" onClick={onToggleAutoUse} disabled={pending}>
              {pool.auto_use ? "Matikan auto-use" : "Aktifkan auto-use"}
            </Button>
            <Button size="sm" variant="ghost" render={<a href="/api/proxies/active" download />}>
              Unduh active.txt ({pool.active_txt_lines})
            </Button>
            <Button size="sm" variant="destructive" onClick={onClear} disabled={pending || !pool.items.length}>
              Hapus semua
            </Button>
          </div>

          {mode === "files" ? (
            <div className="space-y-2">
              <div
                className="border-muted-foreground/30 rounded-lg border border-dashed p-4 text-center text-sm"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  onFiles(event.dataTransfer.files);
                }}
              >
                Tarik beberapa file proxy (.txt/.csv) ke sini, atau
                <button type="button" className="text-primary ml-1 underline" onClick={() => fileRef.current?.click()}>
                  pilih file
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept=".txt,.csv,text/plain"
                  className="hidden"
                  onChange={(event) => onFiles(event.target.files)}
                />
              </div>
              {pending ? (
                <p className="text-muted-foreground flex items-center gap-2 text-xs">
                  <ClipzySpinner size="xs" variant="ring" /> Membaca & menormalkan file…
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2">
              <textarea
                className="border-input bg-background min-h-32 w-full rounded-md border p-2 font-mono text-xs"
                placeholder={"host:port\nhost:port:user:pass\nuser:pass@host:port\nsocks5://host:port\nlabel|host:port"}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
              <Button size="sm" variant="outline" onClick={onParseText} disabled={!text.trim() || pending}>
                Parse & preview
              </Button>
            </div>
          )}

          {preview ? (
            <div className="space-y-2 rounded-lg border p-3 text-sm">
              <p className="font-medium">
                {preview.valid} proxy valid · {preview.duplicate} duplikat · {preview.errors.length} gagal
                {preview.files?.length ? " · " + preview.files.length + " file" : ""}
              </p>
              {preview.errors.length ? (
                <div className="text-muted-foreground max-h-24 overflow-auto text-xs">
                  {preview.errors.slice(0, 8).map((row) => (
                    <p key={row.line + row.value}>
                      baris {row.line}: <code>{row.value}</code> — {row.reason}
                    </p>
                  ))}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={onStartFilter} disabled={filtering || pending || !preview.valid} className="gap-2">
                  {filtering ? <ClipzySpinner size="xs" variant="ring" /> : null}
                  {filtering ? "Menguji proxy…" : "START FILTER ACTIVE PROXY"}
                </Button>
                <Button size="sm" variant="outline" onClick={onSaveOnly} disabled={pending || filtering}>
                  Simpan tanpa uji
                </Button>
              </div>
            </div>
          ) : null}

          {filtering && status ? (
            <div className="space-y-1">
              <div className="bg-muted h-2 w-full overflow-hidden rounded-full">
                <div className="bg-primary h-full transition-all" style={{ width: progress + "%" }} />
              </div>
              <p className="text-muted-foreground text-xs">
                {status.tested}/{status.total} diuji · {status.active} aktif · {status.dead} mati
              </p>
            </div>
          ) : null}

          {message ? <p className="text-sm text-emerald-600">{message}</p> : null}
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Proxy aktif ({activeItems.length})</CardTitle>
          <CardDescription>
            Disimpan sebagai satu file <code>active.txt</code> dan dipakai otomatis oleh worker.
            {pool.updated_at ? " Diperbarui: " + pool.updated_at : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Proxy</TableHead>
                <TableHead>Skema</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead>Exit IP</TableHead>
                <TableHead>Dicek</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {activeItems.length ? (
                activeItems.map((item) => (
                  <TableRow key={item.url}>
                    <TableCell className="font-mono text-xs">{item.url}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{item.scheme}</Badge>
                    </TableCell>
                    <TableCell className="text-xs tabular-nums">
                      {item.latency_ms ? item.latency_ms + " ms" : "-"}
                    </TableCell>
                    <TableCell className="text-xs">{item.exit_ip || "-"}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {item.last_checked || "-"}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-muted-foreground text-center">
                    Belum ada proxy aktif. Upload file lalu jalankan START FILTER.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
