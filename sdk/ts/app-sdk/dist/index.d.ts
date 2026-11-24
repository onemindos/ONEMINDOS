import type { OneMind, RequestActionInput, components, paths } from '@onemind/sdk';
type Series = NonNullable<paths['/v1/series']['get']['parameters']['query']>;
type Notify = components['schemas']['SendIn'];
type Declaration = Record<string, unknown>;
export interface AppDeclarations {
    tools?: readonly Declaration[];
    search?: Declaration;
    notifications?: readonly Declaration[];
    layers?: readonly Declaration[];
    settings?: Declaration;
}
/** Keep literal manifest declarations available to the app manifest validator. */
export declare function defineApp<T extends AppDeclarations>(declarations: T): T;
export declare class AppClient {
    #private;
    constructor(gateway: OneMind, ownSecrets?: ReadonlyMap<string, string>);
    requestAction(input: RequestActionInput): Promise<{
        approval?: components["schemas"]["ApprovalCard"] | null;
        approved_by?: string | null;
        created_at: string;
        decided_at: string | null;
        decided_by: components["schemas"]["PrincipalRef"] | null;
        expires_at: string;
        id: string;
        idempotency_key: string;
        params: {
            [key: string]: unknown;
        };
        plan?: {
            [key: string]: unknown;
        } | null;
        plan_sha256?: string | null;
        progress?: {
            [key: string]: unknown;
        } | null;
        requested_by: components["schemas"]["PrincipalRef"];
        result: {
            [key: string]: unknown;
        } | null;
        risk?: string | null;
        state: string;
        type: string;
        updated_at: string;
        version: number;
    } & {
        [key: string]: unknown;
    }>;
    fileRoots(): Promise<unknown>;
    notify(body: Notify): Promise<unknown>;
    series(query: Series): Promise<{
        at: string;
        value: number;
    }[]>;
    /** Secrets already delivered by the host for this app. There is no app ID or gateway secret lookup. */
    ownSecret(name: string): string | undefined;
}
export {};
