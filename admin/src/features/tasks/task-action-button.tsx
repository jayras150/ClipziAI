'use client';

import { useActionState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { cancelTask, retryTask, type TaskActionResult } from '@/app/dashboard/tasks/actions';

type TaskActionButtonProps = {
  action: 'cancel' | 'retry';
  taskId: string;
  taskStatus: string;
  className?: string;
};

const TERMINAL = new Set(['completed', 'error', 'cancelled']);

export function TaskActionButton({
  action,
  taskId,
  taskStatus,
  className = ''
}: TaskActionButtonProps) {
  const isTerminal = TERMINAL.has(taskStatus);

  const [, formAction, isPending] = useActionState(
    async (_prev: TaskActionResult | null, formData: FormData) => {
      const result = action === 'cancel' ? await cancelTask(formData) : await retryTask(formData);
      if (result.ok) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
      return result;
    },
    null
  );

  const label = action === 'cancel' ? 'Batalkan task' : 'Ulangi task';
  const variant = action === 'cancel' ? 'destructive' : 'secondary';

  // Task terminal tidak bisa dibatalkan/diulang: tombol disabled dengan alasan.
  if (isTerminal) {
    const reason =
      taskStatus === 'completed'
        ? 'Task sudah selesai'
        : taskStatus === 'error'
          ? 'Task gagal — gunakan Ulangi task'
          : 'Task sudah dibatalkan';
    return (
      <form action={formAction} className='inline'>
        <input type='hidden' name='tid' value={taskId} />
        <Button
          size='sm'
          variant={variant}
          disabled
          title={reason}
          className={className}
        >
          {label}
        </Button>
      </form>
    );
  }

  return (
    <form action={formAction} className='inline'>
      <input type='hidden' name='tid' value={taskId} />
      <Button
        size='sm'
        variant={variant}
        disabled={isPending}
        className={className}
      >
        {isPending ? 'Memproses…' : label}
      </Button>
    </form>
  );
}
