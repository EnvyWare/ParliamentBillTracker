import { ROUTES } from '../model/routes';

/**
 * Loading placeholder shaped like the pipeline it is about to become.
 *
 * Matching the final layout keeps the page from jumping when the data
 * arrives, which is what keeps cumulative layout shift low.
 */
export function PipelineSkeleton(): React.JSX.Element {
  return (
    <div className="shell" aria-busy="true" aria-live="polite">
      <p className="visually-hidden">Loading Bill data.</p>
      <div className="routes">
        {ROUTES.map((route) => (
          <div className="route" key={route.id}>
            <div className="route__summary">
              <span className="skeleton skeleton--line" style={{ width: '18rem' }} />
            </div>
            <div className="route__body">
              {route.phases.map((phase) => (
                <div className="phase phase--both" key={phase.id}>
                  <span className="skeleton skeleton--line" style={{ width: '12rem' }} />
                  <div className="phase__stages">
                    {phase.steps.map((step) => (
                      <div className="bucket" key={step.node}>
                        <div className="bucket__header">
                          <span className="skeleton skeleton--line" style={{ width: '70%' }} />
                          <span className="skeleton skeleton--line" style={{ width: '40%' }} />
                        </div>
                        <div className="bucket__list">
                          <span className="skeleton skeleton--card" />
                          <span className="skeleton skeleton--card" />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
