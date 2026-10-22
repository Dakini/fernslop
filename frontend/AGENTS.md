<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture
- All backend calls go through `getServices()` in `src/services/index.ts`, typed by the `GardenService` interface; UI never talks to storage directly — so a real backend can replace the mock by swapping one implementation.
- `src/services/mock/` is a full in-browser mock (localStorage + cross-tab sync) used until a real backend exists; keep it in step with the interface and its tests.
- Care-ring maths lives in `src/services/care.ts` as pure functions; intervals come only from plant data.
- Data routes use `ssr: false` because the mock reads browser storage.
