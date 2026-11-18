'use client';

import { useEffect, useMemo, useRef, useState, useTransition } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { fetchWorkerLines, type WorkerLogLine } from '@/app/dashboard/workers/actions';

/** Terminal kecil: log pipeline dari DALAM instance worker (bukan Vast logs). */
export default function WorkerLogViewer({ initialTaskId = '' }: { initialTaskId?: string }) {
  const [taskId, setTaskId] = useState(initialTaskId);
  const [lines, setLines] = useState<WorkerLogLine[]>([]);
  const [level, setLevel] = useState('');
  const [error, setError] = useState('');
  const [auto, setAuto] = useState(true);
  const [pending, startTransition] = useTransition();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const load = (reset = false) => {
    if (!taskId.trim()) return;
    const after = reset ? 0 : lines.length ? lines[lines.length - 1].seq : 0;
    startTransition(async () => {
      const result = await fetchWorkerLines(taskId.trim(), after, level);
      setError(result.error || '');
      setLines((prev) => (reset ? result.items : [...prev, ...result.items].slice(-2000)));
    });
  };

  useEffect(() => {
    if (!auto || !taskId.trim()) return;
    const timer = window.setInterval(() => load(false), 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, taskId, level, lines.length]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines.length]);

  const text = useMemo(
    () => lines.map((line) => `[${line.created_at || ''}] ${line.level}${line.stage ? ' ' + line.stage : ''} ${line.message}`).join('\n'),
    [lines]
  );

  const download = () => {
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `worker-${taskId.slice(0, 8) || 'log'}.log`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Worker Logs (log pipeline asli)</CardTitle>
        <CardDescription>
          Dikirim langsung dari dalam instance (stdout/stderr, stage, exit code, dmesg, nvidia-smi).
          Bukan log Vast.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap items-end gap-2'>
          <div className='min-w-[260px] flex-1'>
            <label className='text-xs font-medium'>Task ID</label>
            <Input value={taskId} onChange={(event) => setTaskId(event.target.value)} placeholder='0eadfc7d-…' />
          </div>
          <div>
            <label className='text-xs font-medium'>Level</label>
            <select
              className='border-input bg-background mt-1 h-9 rounded-md border px-3 text-sm'
              value={level}
              onChange={(event) => setLevel(event.target.value)}
            >
              <option value=''>Semua</option>
              <option value='ERROR'>ERROR</option>
              <option value='INFO'>INFO</option>
            </select>
          </div>
          <Button variant='outline' onClick={() => load(true)} disabled={pending}>
            Muat ulang
          </Button>
          <Button variant='ghost' onClick={() => setAuto((prev) => !prev)}>
            Auto {auto ? 'ON' : 'OFF'}
          </Button>
          <Button variant='secondary' onClick={download} disabled={!lines.length}>
            Download .log
          </Button>
        </div>

        {error ? <p className='text-destructive text-xs'>{error}</p> : null}

        <pre className='max-h-[420px] overflow-auto rounded-md bg-black p-3 font-mono text-[11px] leading-relaxed text-emerald-300'>
          {lines.length ? text : 'Belum ada log dari worker — instance mungkin belum mulai atau task ID salah.'}
          <div ref={bottomRef} />
        </pre>
      </CardContent>
    </Card>
  );
}
