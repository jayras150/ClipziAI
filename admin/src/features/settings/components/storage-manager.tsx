"use client";

import { useState, useTransition } from "react";

import {
  cancelStorageSync,
  deleteStorage,
  fetchStorage,
  locateStorageObject,
  saveStorage,
  setMirrorStorages,
  setPrimaryStorage,
  startStorageSync,
  storageSyncStatus,
  testStorage,
  type StorageConfigView,
  type StorageItem,
  type SyncJobStatus
} from "@/app/dashboard/settings/storage-actions";
import { StorageCloudflare } from "@/features/settings/components/storage-cloudflare";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ClipzySpinner } from "@/components/ui/clipzy-spinner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";

const EMPTY_FORM = {
  id: "",
  name: "",
  provider: "r2",
  bucket: "",
  endpoint: "",
  region: "auto",
  public_domain: "",
  path_prefix: "",
  access_key: "",
  secret_key: "",
  enabled: true
};

export function StorageManager({ initial }: { initial: StorageConfigView }) {
  const [config, setConfig] = useState<StorageConfigView>(initial);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState("");
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string>("");
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<"providers" | "cloudflare">("providers");
  const [syncJob, setSyncJob] = useState<SyncJobStatus | null>(null);
  const [syncMode, setSyncMode] = useState<"push" | "reconcile" | "heal">("push");
  const [locateKey, setLocateKey] = useState("");
  const [locate, setLocate] = useState<Awaited<ReturnType<typeof locateStorageObject>> | null>(
    null
  );

  const providers = config.providers || [];
  const preset = providers.find((row) => row.id === form.provider);

  const set = (key: keyof typeof form, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const resetForm = () => {
    setForm({ ...EMPTY_FORM });
    setEditing(false);
  };

  const onProviderChange = (provider: string) => {
    const meta = providers.find((row) => row.id === provider);
    setForm((prev) => ({
      ...prev,
      provider,
      endpoint: meta?.endpoint || "",
      region: meta?.region || "auto"
    }));
  };

  const onEdit = (item: StorageItem) => {
    setForm({
      id: item.id,
      name: item.name,
      provider: item.provider,
      bucket: item.bucket,
      endpoint: item.endpoint,
      region: item.region,
      public_domain: item.public_domain,
      path_prefix: item.path_prefix,
      access_key: "",
      secret_key: "",
      enabled: item.enabled
    });
    setEditing(true);
  };

  const onSave = () => {
    setError("");
    setMessage("");
    startTransition(async () => {
      try {
        const payload: Record<string, unknown> = {
          name: form.name || preset?.label || "Storage",
          provider: form.provider,
          bucket: form.bucket,
          endpoint: form.endpoint,
          region: form.region,
          public_domain: form.public_domain,
          path_prefix: form.path_prefix,
          enabled: form.enabled
        };
        if (form.id) payload.id = form.id;
        if (form.access_key) payload.access_key = form.access_key;
        if (form.secret_key) payload.secret_key = form.secret_key;
        const fresh = await saveStorage(payload);
        setConfig(fresh);
        if (fresh.warnings?.length) {
          setWarning(fresh.warnings.join(" "));
        } else {
          setWarning("");
        }
        setMessage("Storage disimpan. Kredensial tersimpan terenkripsi (AES-256-GCM).");
        resetForm();
      } catch (err) {
        setError((err as Error).message);
      }
    });
  };

  const onTest = (item: StorageItem) => {
    setBusy(item.id);
    setError("");
    setMessage("");
    startTransition(async () => {
      try {
        const result = await testStorage(item.id);
        setConfig(result.storage);
        if (result.result.ok) {
          setWarning(result.result.note || "");
          setMessage("Koneksi " + item.name + " OK (" + result.result.latency_ms + " ms)");
        } else {
          setWarning(result.result.hint || "");
          setMessage("Gagal: " + (result.result.error || "tidak diketahui"));
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy("");
      }
    });
  };

  const onPrimary = (id: string) => {
    startTransition(async () => {
      const fresh = await setPrimaryStorage(id);
      setConfig(fresh);
      setMessage("Primary storage diperbarui.");
    });
  };

  const onToggleMirror = (id: string) => {
    const current = config.mirror_ids || [];
    const next = current.includes(id) ? current.filter((row) => row !== id) : [...current, id];
    startTransition(async () => {
      const fresh = await setMirrorStorages(next);
      setConfig(fresh);
      setMessage("Daftar mirror diperbarui.");
    });
  };

  const onDelete = (id: string) => {
    startTransition(async () => {
      const fresh = await deleteStorage(id);
      setConfig(fresh);
      setMessage("Storage dihapus.");
    });
  };

  const pollSync = async () => {
    for (let attempt = 0; attempt < 240; attempt += 1) {
      const status = await storageSyncStatus();
      setSyncJob(status);
      if (status.state !== "running") return status;
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    return null;
  };

  const onSync = () => {
    setBusy("sync");
    setMessage("");
    setError("");
    startTransition(async () => {
      try {
        const started = await startStorageSync(syncMode, 50, 500);
        if (!started.started) {
          setError(started.message || "Sync tidak bisa dimulai");
          return;
        }
        const finalStatus = await pollSync();
        if (finalStatus) {
          setMessage(
            `Sync ${finalStatus.state}: ${finalStatus.copied} disalin, ${finalStatus.skipped} sudah ada, ${finalStatus.failed} gagal` +
              (finalStatus.error ? ` — ${finalStatus.error}` : "")
          );
        }
        setConfig(await fetchStorage());
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy("");
      }
    });
  };

  const onCancelSync = () => {
    startTransition(async () => {
      await cancelStorageSync();
      setMessage("Permintaan batal dikirim.");
    });
  };

  const onLocate = () => {
    if (!locateKey.trim()) return;
    setBusy("locate");
    setError("");
    startTransition(async () => {
      try {
        setLocate(await locateStorageObject(locateKey.trim()));
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy("");
      }
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={tab === "providers" ? "default" : "outline"}
          onClick={() => setTab("providers")}
        >
          Provider
        </Button>
        <Button
          size="sm"
          variant={tab === "cloudflare" ? "default" : "outline"}
          onClick={() => setTab("cloudflare")}
        >
          Cloudflare CDN
        </Button>
      </div>

      {tab === "cloudflare" ? (
        <StorageCloudflare config={config} onChange={setConfig} />
      ) : (
        <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <CardTitle>Penyimpanan objek</CardTitle>
            <CardDescription>
              Semua upload (klip, thumbnail, SRT, branding, watermark) ditulis ke <strong>Primary</strong> lalu
              direplikasi ke <strong>mirror</strong>. Bisa lebih dari satu provider.
            </CardDescription>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant="outline">{config.items.length} storage</Badge>
            <div className="flex items-center gap-2">
              <Select
                value={syncMode}
                onValueChange={(value: string | null) => setSyncMode((value || "push") as typeof syncMode)}
              >
                <SelectTrigger className="h-8 w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="push">Push ke mirror</SelectItem>
                  <SelectItem value="reconcile">Rekonsiliasi 2 arah</SelectItem>
                  <SelectItem value="heal">Pulihkan primary</SelectItem>
                </SelectContent>
              </Select>
              <Button size="sm" variant="outline" className="gap-2" onClick={onSync} disabled={pending || busy === "sync"}>
                {busy === "sync" ? <ClipzySpinner size="xs" variant="ring" /> : null}
                Sync
              </Button>
              {busy === "sync" ? (
                <Button size="sm" variant="ghost" onClick={onCancelSync}>
                  Batal
                </Button>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {config.items.length ? (
            config.items.map((item) => {
              const isPrimary = config.primary_id === item.id;
              const isMirror = (config.mirror_ids || []).includes(item.id);
              const providerLabel = providers.find((row) => row.id === item.provider)?.label || item.provider;
              const check = item.last_check;
              return (
                <div key={item.id} className="space-y-2 rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{item.name}</span>
                    <Badge variant="outline">{providerLabel}</Badge>
                    {isPrimary ? <Badge variant="secondary">primary</Badge> : null}
                    {isMirror ? <Badge variant="outline">mirror</Badge> : null}
                    {!item.enabled ? <Badge variant="destructive">nonaktif</Badge> : null}
                    {check ? (
                      <Badge variant={check.ok ? "secondary" : "destructive"}>
                        {check.ok ? "ok " + (check.latency_ms ?? "?") + " ms" : "gagal"}
                      </Badge>
                    ) : null}
                  </div>
                  <p className="text-muted-foreground text-xs">
                    bucket <code>{item.bucket}</code> · {item.endpoint || "endpoint default"} · region {item.region}
                    {item.public_domain ? " · publik: " + item.public_domain : ""}
                    {item.path_prefix ? " · prefix: " + item.path_prefix : ""}
                  </p>
                  {check && !check.ok && check.error ? (
                    <p className="text-destructive text-xs">{check.error}</p>
                  ) : null}
                  {check && !check.ok && check.hint ? (
                    <p className="text-xs text-amber-600">{check.hint}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="gap-2" onClick={() => onTest(item)} disabled={pending || busy === item.id}>
                      {busy === item.id ? <ClipzySpinner size="xs" variant="ring" /> : null}
                      Uji
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => onPrimary(item.id)} disabled={pending || isPrimary}>
                      Jadikan primary
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => onToggleMirror(item.id)} disabled={pending || isPrimary}>
                      {isMirror ? "Lepas mirror" : "Jadikan mirror"}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => onEdit(item)} disabled={pending}>
                      Edit
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => onDelete(item.id)} disabled={pending || isPrimary}>
                      Hapus
                    </Button>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="text-muted-foreground text-sm">
              Belum ada storage. Tambah di bawah (bila env R2_* ada, entri otomatis dibuat saat startup).
            </p>
          )}

          {message ? <p className="text-sm text-emerald-600">{message}</p> : null}
          {warning ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm text-amber-700 dark:text-amber-400">
              {warning}
            </p>
          ) : null}
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
        </CardContent>
      </Card>

      {syncJob && syncJob.state !== "idle" ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Progres sync</CardTitle>
              <CardDescription>
                mode <strong>{syncJob.mode}</strong>
                {syncJob.current ? ` · ${syncJob.current}` : ""}
                {syncJob.error ? ` · ${syncJob.error}` : ""}
              </CardDescription>
            </div>
            <Badge variant={syncJob.state === "running" ? "secondary" : "outline"}>
              {syncJob.state}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-muted-foreground flex flex-wrap gap-3 text-xs">
              <span>disalin {syncJob.copied}</span>
              <span>sudah ada {syncJob.skipped}</span>
              <span>gagal {syncJob.failed}</span>
              <span>{(syncJob.bytes / (1024 * 1024)).toFixed(1)} MB</span>
            </div>
            {syncJob.per_mirror.map((row) => (
              <div key={row.id} className="rounded-md border p-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{row.provider}</Badge>
                  <span className="font-medium">{row.name || row.id}</span>
                  <span className="text-muted-foreground">
                    {row.copied} disalin · {row.skipped} sudah ada · {row.failed} gagal
                  </span>
                  {row.error ? <span className="text-destructive">{row.error}</span> : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cari file di semua storage</CardTitle>
          <CardDescription>
            Cek apakah sebuah objek ada di primary atau mirror — dipakai untuk memastikan file
            benar-benar tersimpan sebelum dipulihkan.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[260px] flex-1 space-y-2">
              <Label>Object key</Label>
              <Input
                value={locateKey}
                onChange={(event) => setLocateKey(event.target.value)}
                placeholder="clips/<task-id>/<clip>.mp4"
              />
            </div>
            <Button size="sm" className="gap-2" onClick={onLocate} disabled={pending || busy === "locate"}>
              {busy === "locate" ? <ClipzySpinner size="xs" variant="ring" /> : null}
              Cari
            </Button>
          </div>
          {locate ? (
            <div className="space-y-2 text-xs">
              <p className="text-muted-foreground">
                Ditemukan di {locate.found} dari {locate.locations.length} storage.
              </p>
              {locate.locations.map((row) => (
                <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
                  <Badge variant={row.exists ? "secondary" : "outline"}>
                    {row.exists ? "ada" : "tidak ada"}
                  </Badge>
                  <span className="font-medium">{row.name || row.id}</span>
                  <span className="text-muted-foreground">{row.provider}</span>
                  {row.size ? <span className="text-muted-foreground">{(row.size / 1048576).toFixed(1)} MB</span> : null}
                  {row.error ? <span className="text-destructive">{row.error}</span> : null}
                  {row.url ? (
                    <a className="text-primary underline" href={row.url} target="_blank" rel="noreferrer">
                      buka
                    </a>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{editing ? "Edit storage" : "Tambah storage"}</CardTitle>
          <CardDescription>
            Pilih provider → endpoint & region terisi otomatis. Kredensial disimpan terenkripsi; kosongkan
            saat edit bila tidak ingin mengubah.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Provider</Label>
            <select
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              value={form.provider}
              onChange={(event) => onProviderChange(event.target.value)}
            >
              {providers.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.label}
                </option>
              ))}
            </select>
            {preset?.hint ? <p className="text-muted-foreground text-xs">{preset.hint}</p> : null}
          </div>
          <div className="space-y-2">
            <Label>Nama</Label>
            <Input value={form.name} onChange={(event) => set("name", event.target.value)} placeholder="R2 utama" />
          </div>
          <div className="space-y-2">
            <Label>Bucket</Label>
            <Input value={form.bucket} onChange={(event) => set("bucket", event.target.value)} placeholder="clipzi" />
          </div>
          <div className="space-y-2">
            <Label>Endpoint</Label>
            <Input value={form.endpoint} onChange={(event) => set("endpoint", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Region</Label>
            <Input value={form.region} onChange={(event) => set("region", event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Public domain (opsional)</Label>
            <Input
              value={form.public_domain}
              onChange={(event) => set("public_domain", event.target.value)}
              placeholder="https://cdn.domain.com"
            />
          </div>
          <div className="space-y-2">
            <Label>Path prefix (opsional)</Label>
            <Input
              value={form.path_prefix}
              onChange={(event) => set("path_prefix", event.target.value)}
              placeholder="clips"
            />
          </div>
          <div className="space-y-2">
            <Label>Access key</Label>
            <Input
              value={form.access_key}
              onChange={(event) => set("access_key", event.target.value)}
              placeholder={editing ? "biarkan kosong bila tidak diubah" : "AKIA..."}
            />
          </div>
          <div className="space-y-2">
            <Label>Secret key</Label>
            <Input
              type="password"
              value={form.secret_key}
              onChange={(event) => set("secret_key", event.target.value)}
              placeholder={editing ? "biarkan kosong bila tidak diubah" : "••••••••"}
            />
          </div>
          <div className="flex items-end gap-2 md:col-span-2">
            <Button className="gap-2" onClick={onSave} disabled={pending || !form.bucket}>
              {pending ? <ClipzySpinner size="xs" variant="ring" /> : null}
              {editing ? "Simpan perubahan" : "Tambah storage"}
            </Button>
            {editing ? (
              <Button variant="ghost" onClick={resetForm} disabled={pending}>
                Batal
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
        </>
      )}
    </div>
  );
}
