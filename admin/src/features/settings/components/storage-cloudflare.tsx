"use client";

/**
 * Tab "Cloudflare CDN" di Settings › Storage (mode manual: CNAME dipasang user).
 */
import { useState, useTransition } from "react";

import {
  checkStorageDomain,
  setCustomDomain,
  type DomainCheck,
  type StorageConfigView
} from "@/app/dashboard/settings/storage-actions";
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

export function StorageCloudflare({
  config,
  onChange
}: {
  config: StorageConfigView;
  onChange: (next: StorageConfigView) => void;
}) {
  const r2Items = config.items.filter((item) => item.provider === "r2");
  const [itemId, setItemId] = useState<string>(r2Items[0]?.id || "");
  const [domain, setDomain] = useState<string>(r2Items[0]?.public_domain || "");
  const [check, setCheck] = useState<DomainCheck | null>(null);
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState<"" | "save" | "test">("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const cleanDomain = (value: string) =>
    value.trim().toLowerCase().replace(/^[a-z]+:\/\//, "").split("/")[0];

  const onSelectItem = (value: string | null) => {
    const next = value || "";
    setItemId(next);
    const item = r2Items.find((row) => row.id === next);
    setDomain(item?.public_domain || "");
    setCheck(null);
    setMessage("");
    setError("");
  };

  const onTest = () => {
    setError("");
    setMessage("");
    setBusy("test");
    startTransition(async () => {
      try {
        const result = await checkStorageDomain(cleanDomain(domain), itemId || undefined);
        setCheck(result);
        setMessage(
          result.dns_ok && result.reachable
            ? "Domain aktif dan bisa diakses."
            : "Domain belum siap — lihat catatan di bawah."
        );
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy("");
      }
    });
  };

  const onSave = () => {
    if (!itemId) return;
    setError("");
    setMessage("");
    setBusy("save");
    startTransition(async () => {
      try {
        const result = await setCustomDomain(itemId, cleanDomain(domain));
        onChange(result.storage);
        setCheck(result.result);
        setMessage("Custom domain disimpan sebagai public domain storage.");
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy("");
      }
    });
  };

  const selected = r2Items.find((row) => row.id === itemId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cloudflare CDN (custom domain)</CardTitle>
        <CardDescription>
          Pakai subdomain sendiri (mis. <code>cdn.domain.com</code>) untuk URL klip, supaya tidak
          bergantung pada <code>r2.dev</code> yang dibatasi Cloudflare.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {r2Items.length ? (
          <>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Storage R2</Label>
                <Select value={itemId} onValueChange={onSelectItem}>
                  <SelectTrigger>
                    <SelectValue placeholder="Pilih storage R2" />
                  </SelectTrigger>
                  <SelectContent>
                    {r2Items.map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.name} · {item.bucket}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Custom domain</Label>
                <Input
                  value={domain}
                  onChange={(event) => setDomain(event.target.value)}
                  placeholder="cdn.domain.com"
                />
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                className="gap-2"
                onClick={onSave}
                disabled={pending || busy !== "" || !domain.trim()}
              >
                {busy === "save" ? <ClipzySpinner size="xs" variant="ring" /> : null}
                Sambungkan domain
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-2"
                onClick={onTest}
                disabled={pending || busy !== "" || !domain.trim()}
              >
                {busy === "test" ? <ClipzySpinner size="xs" variant="ring" /> : null}
                Uji domain (DNS + HTTPS)
              </Button>
            </div>

            {selected?.public_domain ? (
              <p className="text-muted-foreground text-xs">
                Public domain aktif: <code>{selected.public_domain}</code>
              </p>
            ) : null}

            {check ? (
              <div className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={check.dns_ok ? "secondary" : "outline"}>
                    DNS {check.dns_ok ? "OK" : "gagal"}
                  </Badge>
                  <Badge variant={check.cert_ok ? "secondary" : "outline"}>
                    Sertifikat {check.cert_ok ? "OK" : "gagal"}
                  </Badge>
                  <Badge variant={check.reachable ? "secondary" : "outline"}>
                    HTTP {check.http_status ?? "—"}
                  </Badge>
                  {check.resolved?.length ? (
                    <span className="text-muted-foreground text-xs">
                      IP: {check.resolved.slice(0, 3).join(", ")}
                    </span>
                  ) : null}
                </div>
                {check.cname_target ? (
                  <p className="text-muted-foreground mt-2 text-xs">
                    CNAME target: <code>{check.cname_target}</code>
                  </p>
                ) : null}
                {check.hint ? <p className="mt-2 text-amber-600 text-xs">{check.hint}</p> : null}
              </div>
            ) : null}

            {message ? <p className="text-sm text-emerald-600">{message}</p> : null}
            {error ? <p className="text-destructive text-sm">{error}</p> : null}

            <div className="bg-muted/40 space-y-2 rounded-md border p-3 text-xs leading-relaxed">
              <p className="font-medium">Langkah memasang (manual, ±2 menit)</p>
              <ol className="text-muted-foreground list-decimal space-y-1 pl-4">
                <li>
                  Cloudflare → <strong>R2</strong> → bucket <code>{selected?.bucket || "…"}</code> →{" "}
                  <strong>Settings</strong> → <strong>Custom Domains</strong> → Connect Domain.
                </li>
                <li>Isi subdomain yang sama dengan kolom di atas (mis. cdn.domain.com).</li>
                <li>
                  Cloudflare membuat CNAME ke{" "}
                  <code>
                    {check?.cname_target ||
                      `${selected?.bucket || "<bucket>"}.<account_id>.r2.cloudflarestorage.com`}
                  </code>{" "}
                  (manual: tipe CNAME, proxy ON).
                </li>
                <li>Tunggu sertifikat Active, lalu tekan <strong>Uji domain</strong>.</li>
                <li>Klik <strong>Sambungkan domain</strong> agar URL klip memakai domain ini.</li>
              </ol>
            </div>
          </>
        ) : (
          <p className="text-muted-foreground text-sm">
            Belum ada storage provider Cloudflare R2. Tambahkan dulu di tab{" "}
            <strong>Provider</strong>.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

