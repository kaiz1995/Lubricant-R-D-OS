import { useNavigate } from "react-router-dom";
import { useLayoutStore } from "@/lib/layout";
import { sessionProject } from "@/lib/projectScope";
import { useIsMobile } from "@/lib/useIsMobile";
import { isGatewayWeb } from "@/lib/webMode";

/** Open an existing session from a page (Projects, History, Runs, …). On the
 *  desktop the route alone shows nothing — the panes do — so the session is put
 *  on screen first (its own preview Screen, in its project, or wherever it is
 *  already open), exactly as a sidebar click does. Phone and web are
 *  single-pane: the route is enough. */
export function useOpenSession(): (sessionId: string) => void {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  return (sessionId) => {
    if (!isMobile && !isGatewayWeb)
      useLayoutStore.getState().openSessionEphemeral(sessionId, sessionProject(sessionId));
    navigate(`/live/${sessionId}`);
  };
}
