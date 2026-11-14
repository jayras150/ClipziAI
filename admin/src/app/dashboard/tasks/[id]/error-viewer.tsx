'use client';

import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';

export type AttemptRow = {
  id: string;
  attempt_no: number;
  runner_type: string | null;
  runner_id: string | null;
  yt_dlp_version: string | null;
  extractor_client: string | null;
  format_selector: string | null;
  cookie_id: string | null;
  cookie_status: string | null;
  http_status: number | null;
  error_category: string | null;
  error_message: string | null;
  stack_trace: string | null;
  duration_ms: number | null;
  created_at: string | null;
};

function buildLog(taskId: string, attempts: AttemptRow[], errorMessage: string | null) {
  const lines = [
    `Task ID: ${taskId}`,
    `Error (technical): ${errorMessage || '-'}`,
    `Attempts: ${attempts.length}`,
    ''
  ];
  for (const row of attempts) {
    lines.push(`--- attempt #${row.attempt_no} (${row.created_at || '-'}) ---`);
    lines.push(
      `runner=${row.runner_type || '-'} runner_id=${row.runner_id || '-'} yt-dlp=${row.yt_dlp_version || '-'}`
    );
    lines.push(
      `client=${row.extractor_client || '-'} format=${row.format_selector || '-'} cookie=${row.cookie_id || '-'} (${row.cookie_status || '-'})`
    );
    lines.push(`http=${row.http_status ?? '-'} category=${row.error_category || '-'}`);
    lines.push('error:');
    lines.push(row.error_message || '-');
    lines.push('stack:');
    lines.push(row.stack_trace || '-');
    lines.push('');
  }
  return lines.join('\n');
}

export default function ErrorViewer({
  taskId,
  errorMessage,
  attempts
}: {
  taskId: string;
  errorMessage: string | null;
  attempts: AttemptRow[];
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const fullLog = useMemo(() => buildLog(taskId, attempts, errorMessage), [taskId, attempts, errorMessage]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullLog);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const download = () => {
    const blob = new Blob([fullLog], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `task-${taskId}-download.log`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Button size='sm' variant='secondary' onClick={() => setOpen(true)}>
          Lihat log lengkap ({attempts.length} attempt)
        </Button>
        <Button size='sm' variant='outline' onClick={copy}>
          {copied ? 'Tersalin' : 'Copy full log'}
        </Button>
        <Button size='sm' variant='outline' onClick={download}>
          Download log
        </Button>
      </div>
      <pre className='bg-muted mt-2 max-h-40 overflow-auto rounded p-2 text-xs whitespace-pre-wrap'>
        {fullLog}
      </pre>

      {open ? (
        <div
          className='fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4'
          role='presentation'
          onClick={() => setOpen(false)}
        >
          <div
            className='bg-background flex max-h-[90vh] w-full max-w-5xl flex-col gap-3 rounded-lg border p-4 shadow-xl'
            role='dialog'
            aria-modal='true'
            aria-label='Full error log'
            onClick={(event) => event.stopPropagation()}
          >
            <div className='flex flex-wrap items-center justify-between gap-2'>
              <h2 className='text-base font-semibold'>Full download log</h2>
              <div className='flex gap-2'>
                <Button size='sm' variant='outline' onClick={copy}>
                  {copied ? 'Tersalin' : 'Copy'}
                </Button>
                <Button size='sm' variant='outline' onClick={download}>
                  Download
                </Button>
                <Button size='sm' variant='secondary' onClick={() => setOpen(false)}>
                  Tutup
                </Button>
              </div>
            </div>
            <pre className='bg-muted min-h-[200px] flex-1 overflow-auto rounded p-3 text-xs whitespace-pre'>
              {fullLog}
            </pre>
          </div>
        </div>
      ) : null}
    </>
  );
}
