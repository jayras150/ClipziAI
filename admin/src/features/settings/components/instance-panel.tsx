'use client';

import { useState } from 'react';

import VastPanel, { type VastConfigData } from '@/features/settings/components/vast-panel';
import WorkerTemplatePanel from '@/features/settings/components/worker-template-panel';
import WhisperSourcePanel, {
  type WhisperSourceData
} from '@/features/settings/components/whisper-source-panel';
import WhisperModelManager, {
  type WhisperModelsData
} from '@/features/settings/components/whisper-model-manager';
import type { VastTemplateStatus } from '@/app/dashboard/settings/vast/actions';

const TABS = ['Vast.ai', 'Worker Template', 'Model & Storage'] as const;
type Tab = (typeof TABS)[number];

/** Satu halaman "Instance": Vast + template worker tunggal + model/storage. */
export default function InstancePanel({
  config,
  envItems,
  template,
  whisper,
  source,
  initialTab
}: {
  config: VastConfigData;
  envItems: Array<Record<string, unknown>>;
  template: VastTemplateStatus;
  whisper: WhisperModelsData | null;
  source: WhisperSourceData | null;
  initialTab?: string;
}) {
  const start: Tab =
    initialTab === 'model' || initialTab === 'Worker Template'
      ? initialTab === 'model'
        ? 'Model & Storage'
        : 'Worker Template'
      : 'Vast.ai';
  const [tab, setTab] = useState<Tab>(start);

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap gap-2 rounded-lg border p-1'>
        {TABS.map((item) => (
          <button
            key={item}
            type='button'
            onClick={() => setTab(item)}
            className={
              tab === item
                ? 'bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm'
                : 'hover:bg-muted rounded-md px-3 py-1.5 text-sm'
            }
          >
            {item}
          </button>
        ))}
      </div>

      {tab === 'Vast.ai' ? <VastPanel config={config} envItems={envItems} /> : null}

      {tab === 'Worker Template' ? (
        <div className='space-y-4'>
          <WorkerTemplatePanel status={template} />
          <p className='text-muted-foreground text-xs'>
            Template ini otomatis memuat env provider/model yang sedang aktif. Saat mengganti
            provider model atau mengubah env penting, badge “perlu sync” muncul — tekan
            Buat/Update &amp; Aktifkan sekali.
          </p>
        </div>
      ) : null}

      {tab === 'Model & Storage' ? (
        <div className='space-y-4'>
          {source ? <WhisperSourcePanel data={source} /> : null}
          {whisper ? (
            <WhisperModelManager data={whisper} />
          ) : (
            <p className='text-destructive text-sm'>Data model tidak tersedia.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
