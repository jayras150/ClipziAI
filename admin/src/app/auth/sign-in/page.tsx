"use client";

import { useActionState } from 'react';

import { signIn, type AuthState } from '@/app/auth/actions';
import { Button } from '@/components/ui/button';
import { ClipzySpinner } from '@/components/ui/clipzy-spinner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const initialState: AuthState = {};

export default function SignInPage() {
  const [state, formAction, pending] = useActionState(signIn, initialState);

  return (
    <div className='flex min-h-screen items-center justify-center p-6'>
      <Card className='w-full max-w-sm'>
        <CardHeader>
          <CardTitle>ClipzyAI Admin</CardTitle>
          <CardDescription>Masuk dengan akun admin.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='email'>Email</Label>
              <Input id='email' name='email' type='email' autoComplete='email' required />
            </div>
            <div className='space-y-2'>
              <Label htmlFor='password'>Password</Label>
              <Input
                id='password'
                name='password'
                type='password'
                autoComplete='current-password'
                required
              />
            </div>
            {state.error ? (
              <p className='text-destructive text-sm'>{state.error}</p>
            ) : null}
            <Button className='w-full gap-2' type='submit' disabled={pending}>
              {pending ? <ClipzySpinner size='sm' variant='orbit' /> : null}
              {pending ? 'Memverifikasi…' : 'Masuk'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
