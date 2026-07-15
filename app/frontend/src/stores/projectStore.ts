/** Facade for the project workspace store (audit F-11).

Stable import path used by App, sidebar, results, and tests. Implementation lives in
./project.
*/
export {
  initialProjectHistoryWindow,
  initialProjectRevisionWindow,
  useProjectStore,
  type ProjectStoreState
} from "./project";
