import { useEffect, useState } from 'react';
import { api } from './api';

export type Loaded<T> = { data: T | null; error: string | null; loading: boolean };

/** Fetch a JSON endpoint; refetches when `path` changes. `null` path skips the request. */
export function useApi<T>(path: string | null): Loaded<T> {
	const [state, setState] = useState<Loaded<T>>({ data: null, error: null, loading: !!path });
	useEffect(() => {
		if (!path) return setState({ data: null, error: null, loading: false });
		let live = true;
		setState((s) => ({ ...s, loading: true, error: null }));
		api<T>(path)
			.then((data) => live && setState({ data, error: null, loading: false }))
			.catch((e: Error) => live && setState({ data: null, error: e.message, loading: false }));
		return () => {
			live = false;
		};
	}, [path]);
	return state;
}
