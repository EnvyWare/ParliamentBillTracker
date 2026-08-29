/** One Bill's path, and the decisions along it. */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { branchPointsFor, COMMONS_ROUTE, LORDS_ROUTE, orderedSteps } from '../src/model/routes';
import { buildFlowLayout } from '../src/model/flowLayout';
import { buildJourney } from '../src/selectors/journey';
import { billById, renderApp } from './helpers';

describe('route branches', () => {
  it('puts a decision at every point the route can branch', () => {
    const branches = branchPointsFor(COMMONS_ROUTE);
    expect([...branches.keys()]).toEqual([
      'commons_second_reading',
      'commons_third_reading',
      'lords_second_reading',
      'lords_third_reading',
      'ping_pong',
    ]);
  });

  it('names the right Houses for a Lords-first Bill', () => {
    const branches = branchPointsFor(LORDS_ROUTE);
    expect(branches.get('lords_second_reading')?.question).toBe(
      "Does the Lords vote for the Bill's principle?",
    );
    expect(branches.get('commons_third_reading')?.question).toBe(
      'Did the Commons change the Bill?',
    );
  });

  it('offers a way out of the process at every vote', () => {
    for (const route of [COMMONS_ROUTE, LORDS_ROUTE]) {
      const branches = branchPointsFor(route);
      const secondReading = orderedSteps(route)[1]!.node;
      const kinds = branches.get(secondReading)?.outcomes.map((outcome) => outcome.kind);
      expect(kinds).toContain('exit');
    }
  });

  it('models consideration of amendments as a loop, not a single step', () => {
    const kinds = branchPointsFor(COMMONS_ROUTE)
      .get('ping_pong')
      ?.outcomes.map((outcome) => outcome.kind);
    expect(kinds).toContain('loop');
  });

  it('offers the shortcut when the second House does not amend the Bill', () => {
    const kinds = branchPointsFor(COMMONS_ROUTE)
      .get('lords_third_reading')
      ?.outcomes.map((outcome) => outcome.kind);
    expect(kinds).toContain('skip');
  });
});

describe('the drawn diagram', () => {
  /*
   * The layout is authored rather than computed, so these tests pin the parts
   * that carry meaning: which nodes exist, that only the twelve stages are
   * numbered, and that no edge is left dangling.
   */
  it('draws the twelve numbered stages and nothing else numbered', () => {
    const layout = buildFlowLayout(
      'commons',
      COMMONS_ROUTE.phases.flatMap((p) => p.steps).map((s) => s.node),
    );
    const numbered = layout.nodes.filter((node) => node.step !== undefined);
    expect(numbered).toHaveLength(12);
    expect(numbered.map((node) => node.step)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  });

  it('starts and ends at terminals that hold no Bill', () => {
    const layout = buildFlowLayout('commons', []);
    const terminals = layout.nodes.filter((node) => node.kind.startsWith('terminal'));
    expect(terminals.map((node) => node.id).sort()).toEqual(['act', 'falls', 'start']);
    expect(terminals.every((node) => node.step === undefined)).toBe(true);
  });

  it('names the Bill’s own Houses rather than a generic label', () => {
    const commons = buildFlowLayout('commons', []);
    expect(commons.nodes[0]?.lines).toEqual(['Bill introduced in the', 'House of Commons']);
    expect(commons.lanes[0]?.label).toBe('First House · House of Commons');
    expect(commons.lanes[1]?.label).toBe('Second House · House of Lords');

    const lords = buildFlowLayout('lords', []);
    expect(lords.nodes[0]?.lines).toEqual(['Bill introduced in the', 'House of Lords']);
    expect(lords.lanes[0]?.label).toBe('First House · House of Lords');
    expect(lords.lanes[1]?.label).toBe('Second House · House of Commons');
  });

  it('offers a way out of the process at each vote, plus running out of time', () => {
    const layout = buildFlowLayout('commons', []);
    const rejects = layout.edges.filter((edge) => edge.kind === 'reject');
    expect(rejects).toHaveLength(5);
    expect(rejects.filter((edge) => edge.label === 'Rejected')).toHaveLength(4);
    expect(rejects.some((edge) => edge.id === 'pingpong-falls')).toBe(true);
  });

  it('sends consideration of amendments back round rather than onward', () => {
    const layout = buildFlowLayout('commons', []);
    const loop = layout.edges.find((edge) => edge.kind === 'loop');
    expect(loop?.id).toBe('pingpong-decision');
  });

  it('keeps every rejection channel clear of the ping-pong node', () => {
    // A line crossing a box reads as a connection that is not there.
    const layout = buildFlowLayout('commons', []);
    const pingPong = layout.nodes.find((node) => node.id === 'pingpong');
    expect(pingPong).toBeDefined();
    const leftEdge = pingPong!.cx - pingPong!.width / 2;

    for (const edge of layout.edges.filter((e) => e.kind === 'reject' && e.label === 'Rejected')) {
      const channel = Number(/V (\d+)$/.exec(edge.d) === null ? NaN : edge.d.match(/Q (\d+),/)![1]);
      expect(channel).toBeLessThan(leftEdge);
    }
  });

  it('gives every edge a path and every labelled edge a position', () => {
    const layout = buildFlowLayout('commons', []);
    for (const edge of layout.edges) {
      expect(edge.d.startsWith('M ')).toBe(true);
      if (edge.label !== undefined) {
        expect(typeof edge.labelX).toBe('number');
        expect(typeof edge.labelY).toBe('number');
      }
    }
  });
});

describe('building a journey', () => {
  it('marks completed stages, the current stage and the ones not yet reached', () => {
    const journey = buildJourney(billById(9004)); // Commons report stage
    const states = journey.steps.map((step) => step.state);
    expect(states.slice(0, 3)).toEqual(['completed', 'completed', 'completed']);
    expect(states[3]).toBe('current');
    expect(states.slice(4)).toEqual(Array<string>(8).fill('upcoming'));
    expect(journey.completedCount).toBe(3);
    expect(journey.totalCount).toBe(12);
  });

  it('attaches a procedural stage to the stage it ran alongside', () => {
    const journey = buildJourney(billById(9017)); // carried-over Bill
    const committee = journey.steps.find((step) => step.node === 'commons_committee');
    expect(committee?.state).toBe('current');
    expect(committee?.sideEvents.map((entry) => entry.label)).toEqual(['Carry-over motion']);
  });

  it('uses the Lords route for a Lords-origin Bill', () => {
    const journey = buildJourney(billById(9016));
    expect(journey.route?.id).toBe('lords');
    expect(journey.steps[0]?.node).toBe('lords_first_reading');
    expect(journey.steps[6]?.node).toBe('commons_second_reading');
  });

  it('marks a defeated Bill as stopped where it stopped', () => {
    const journey = buildJourney(billById(9024)); // defeated at Lords second reading
    const stopped = journey.steps.find((step) => step.state === 'stopped');
    expect(stopped?.node).toBe('lords_second_reading');
    expect(journey.steps.every((step) => step.state !== 'current')).toBe(true);
  });

  it('records which way a defeated Bill went at the vote', () => {
    const journey = buildJourney(billById(9024));
    const step = journey.steps.find((candidate) => candidate.node === 'lords_second_reading');
    expect(step?.branchAnswer).toBe('No');
  });

  it('records that a ping-pong Bill was amended and has not yet agreed', () => {
    const journey = buildJourney(billById(9011));
    expect(journey.steps.find((step) => step.node === 'lords_third_reading')?.branchAnswer).toBe(
      'Yes',
    );
    expect(journey.steps.find((step) => step.node === 'ping_pong')?.branchAnswer).toBe('No');
  });

  it('records the shortcut when an Act never went through ping-pong', () => {
    const journey = buildJourney(billById(9021)); // Finance Act 2026
    expect(journey.steps.find((step) => step.node === 'lords_third_reading')?.branchAnswer).toBe(
      'No',
    );
    expect(journey.steps.find((step) => step.node === 'ping_pong')?.state).toBe('skipped');
    expect(journey.steps.find((step) => step.node === 'royal_assent')?.state).toBe('completed');
  });

  it('leaves a decision unanswered when the Bill has not reached it', () => {
    const journey = buildJourney(billById(9004));
    expect(
      journey.steps.find((step) => step.node === 'lords_third_reading')?.branchAnswer,
    ).toBeNull();
  });

  it('reports a stage with no recorded sitting as not recorded rather than completed', () => {
    const journey = buildJourney(billById(9022)); // Act with an abbreviated history
    const report = journey.steps.find((step) => step.node === 'commons_report');
    expect(report?.state).toBe('skipped');
    expect(report?.occurrences).toEqual([]);
  });

  it('draws no route for a Bill whose originating House is not stated', () => {
    const journey = buildJourney(billById(9020));
    expect(journey.route).toBeNull();
    expect(journey.steps).toEqual([]);
  });
});

describe('the journey view', () => {
  async function openJourney(billId: number): Promise<void> {
    renderApp({ search: `?bill=${billId}&view=journey` });
    // Present on every journey page, including the one with no route to draw.
    await screen.findByRole('button', { name: /Back to all Bills/ });
  }

  it('opens directly from a shared link', async () => {
    await openJourney(9011);
    expect(screen.getByRole('heading', { level: 2, name: 'Data Protection Bill' })).toBeVisible();
    expect(screen.getByText('10 of 12 stages completed')).toBeVisible();
  });

  it('keeps a single h1 on the page', async () => {
    await openJourney(9011);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('draws the diagram with an accessible summary', async () => {
    const { container } = renderApp({ search: '?bill=9004&view=journey' });
    await screen.findByRole('heading', { level: 2, name: 'Health Standards Bill' });

    const diagram = screen.getByRole('img', { name: /How Health Standards Bill moves through/ });
    expect(diagram).toBeVisible();
    // The picture is never the only source: the route is text as well.
    expect(
      within(container.querySelector('.flow-scroll')!).getByText(/Step 4: commons report/),
    ).toBeInTheDocument();
  });

  it('marks the Bill’s position on the diagram', async () => {
    const { container } = renderApp({ search: '?bill=9004&view=journey' });
    await screen.findByRole('heading', { level: 2, name: 'Health Standards Bill' });

    // Three stages behind it, one current, and the rest not yet reached.
    expect(container.querySelectorAll('.flow__node--completed').length).toBeGreaterThanOrEqual(3);
    expect(container.querySelectorAll('.flow__node--current')).toHaveLength(1);
    expect(container.querySelectorAll('.flow__node--upcoming').length).toBeGreaterThan(0);
  });

  it('draws the rejection a defeated Bill actually took, and no other', async () => {
    const { container } = renderApp({ search: '?bill=9024&view=journey' });
    await screen.findByRole('heading', { level: 2, name: 'Fixed Odds Betting Bill' });

    expect(container.querySelectorAll('.flow__edge--reject.flow__edge--taken')).toHaveLength(1);
    expect(container.querySelectorAll('.flow__node--stopped')).toHaveLength(1);
    expect(container.querySelectorAll('.flow__node--fail')).toHaveLength(1);
  });

  it('marks the exchange loop only when the Houses exchanged more than once', async () => {
    const { container } = renderApp({ search: '?bill=9011&view=journey' });
    await screen.findByRole('heading', { level: 2, name: 'Data Protection Bill' });
    expect(container.querySelectorAll('.flow__edge--loop.flow__edge--taken')).toHaveLength(1);
  });

  it('lists the stage detail beneath the diagram', async () => {
    await openJourney(9004);
    const detail = screen.getByRole('heading', { name: 'Stage by stage' }).closest('section')!;
    expect(within(detail).getAllByRole('heading', { level: 4 })).toHaveLength(12);
    expect(within(detail).getAllByText('Not yet reached').length).toBeGreaterThan(0);
    expect(within(detail).getByText('Current stage')).toBeVisible();
  });

  it('explains the ways a Bill can end outside the route', async () => {
    await openJourney(9004);
    expect(screen.getByRole('heading', { name: 'Ways a Bill can end early' })).toBeVisible();
    expect(screen.getByText(/can withdraw it at any point/)).toBeVisible();
  });

  it('hides the whole-session filters on a single-Bill page', async () => {
    await openJourney(9004);
    expect(screen.queryByLabelText('Search Bills')).toBeNull();
  });

  it('explains itself when there is no route to draw', async () => {
    await openJourney(9020);
    expect(
      screen.getByRole('heading', { name: 'This Bill cannot be placed on a standard route' }),
    ).toBeVisible();
  });

  it('is reachable from the details sheet and returns to the pipeline', async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole('heading', { name: /Starts in the House of Commons/ });

    await user.click(
      screen.getByRole('button', { name: /Health Standards Bill\. View details\./ }),
    );
    await user.click(
      await screen.findByRole('button', { name: /See this Bill’s path through Parliament/ }),
    );

    expect(
      await screen.findByRole('heading', { level: 2, name: 'Health Standards Bill' }),
    ).toBeVisible();
    expect(window.location.search).toBe('?bill=9004&view=journey');

    await user.click(screen.getByRole('button', { name: /Back to all Bills/ }));
    expect(
      await screen.findByRole('heading', { name: /Starts in the House of Commons/ }),
    ).toBeVisible();
  });
});
