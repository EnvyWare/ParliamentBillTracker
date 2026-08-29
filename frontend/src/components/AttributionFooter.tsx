import type { Snapshot } from '../model/types';

const OPEN_PARLIAMENT_LICENCE_URL =
  'https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/';

const REPOSITORY_URL = 'https://github.com/EnvyWare/ParliamentBillTracker';
const ENVYWARE_URL = 'https://envyware.co.uk';

interface AttributionFooterProps {
  readonly snapshot: Snapshot | null;
}

/**
 * Attribution, disclaimer and source links.
 *
 * The Open Parliament Licence sentence and the unofficial disclaimer are both
 * required, and both are always rendered whether or not any data loaded.
 */
export function AttributionFooter({ snapshot }: AttributionFooterProps): React.JSX.Element {
  return (
    <footer className="footer">
      <div className="shell footer__grid">
        <section>
          <h2 className="footer__heading">Data source</h2>
          <p>
            Contains Parliamentary information licensed under the{' '}
            <a href={OPEN_PARLIAMENT_LICENCE_URL} rel="noopener noreferrer" target="_blank">
              Open Parliament Licence v3.0
            </a>
            .
          </p>
          <p>
            Bill data comes from the{' '}
            <a href="https://developer.parliament.uk/" rel="noopener noreferrer" target="_blank">
              UK Parliament Bills API
            </a>
            {snapshot !== null && <> for session {snapshot.source.sessionLabel}</>}. It is collected
            on a schedule and published here as a single static file; your browser never contacts
            Parliament directly.
          </p>
        </section>

        <section>
          <h2 className="footer__heading">About this project</h2>
          <p>
            This is an independent, unofficial project and is not affiliated with or endorsed by UK
            Parliament.
          </p>
          <p>
            It is built and run by{' '}
            <a href={ENVYWARE_URL} rel="noopener noreferrer" target="_blank">
              EnvyWare
            </a>
            , who wanted to see the whole process on one page and could not find it anywhere.
          </p>
          <p>
            The stage a Bill is shown at is derived from published stage identifiers. Some Bills
            follow special procedures that the two standard routes cannot represent; those are
            listed separately rather than being placed by guesswork.
          </p>
          <p>
            The concept was inspired by TLDR News&rsquo;s video on how Bills pass through
            Parliament. No TLDR News material is used in this project.
          </p>
        </section>

        <section>
          <h2 className="footer__heading">Source code</h2>
          <p>
            The project&rsquo;s own code is open source under the MIT licence.{' '}
            <a href={REPOSITORY_URL} rel="noopener noreferrer" target="_blank">
              View the repository on GitHub
            </a>
            .
          </p>
          <p>
            The MIT licence covers this project&rsquo;s original software and assets. It does not
            cover Parliamentary information, which remains under the Open Parliament Licence.
          </p>
          {snapshot !== null && (
            <p>
              <a href="/data/current.json">Download the underlying data</a> (schema version{' '}
              {snapshot.schemaVersion}).
            </p>
          )}
        </section>
      </div>
    </footer>
  );
}
