from pathlib import Path
import re

p = Path('src/app/dashboard/tasks/[id]/page.tsx')
t = p.read_text(encoding='utf-8')

# 1. Imports
t = t.replace("import { adminFetch } from '@/lib/clipzi';", "import { adminFetchSafe } from '@/lib/clipzi';")
t = t.replace("import { cancelTask, retryTask } from '../actions';", "import { TaskActionButton } from '@/features/tasks/task-action-button';")
t = t.replace("import { SubmitButton } from '@/components/ui/submit-button';", "")
t = t.replace("import { AdminErrorCard } from '@/components/admin-error-card';", "")
t = t.replace(
    "import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';",
    "import { AdminErrorCard } from '@/components/admin-error-card';\nimport { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';"
)

# 2. Fetch calls
old_fetch = """  const task = await adminFetch<TaskDetail>(`/api/admin/tasks/${id}`);
  const attempts = await adminFetch<AttemptRow[]>(`/api/admin/tasks/${id}/attempts`);"""
new_fetch = """  const taskResult = await adminFetchSafe<TaskDetail>(`/api/admin/tasks/${id}`);
  const attemptsResult = await adminFetchSafe<AttemptRow[]>(`/api/admin/tasks/${id}/attempts`);
  const task = taskResult.data;
  const attempts = attemptsResult.data ?? [];
  const taskError = taskResult.error;

  if (taskError || !task) {
    return (
      <PageContainer pageTitle='Detail task'>
        <AdminErrorCard title='Gagal memuat detail task' message={taskError ?? 'Task tidak ditemukan.'} />
      </PageContainer>
    );
  }

"""
assert old_fetch in t, 'fetch block not found'
t = t.replace(old_fetch, new_fetch, 1)

# 3. Button block (regex)
old_btn_pattern = r"""          \{ \['error', 'cancelled'\]\.includes\(task\.status\) \? \(\n            <form action=\{retryTask\}\>\n              <input type='hidden' name='tid' value=\{task\.id\} />\n              <SubmitButton size='sm' variant='secondary'>\n                Ulangi task\n              </SubmitButton>\n            </form>\n          \) : \(\n            <form action=\{cancelTask\}\>\n              <input type='hidden' name='tid' value=\{task\.id\} />\n              <SubmitButton size='sm' variant='destructive'>\n                Batalkan task\n              </SubmitButton>\n            </form>\n          \}"""
new_btn = """          <TaskActionButton
            action={['error', 'cancelled'].includes(task.status) ? 'retry' : 'cancel'}
            taskId={task.id}
            taskStatus={task.status}
          />
"""
t2 = re.sub(old_btn_pattern, new_btn, t)
assert t2 != t, 'button block not replaced'
t = t2

p.write_text(t, encoding='utf-8')
print('TASKS_ID_PAGE_OK')
