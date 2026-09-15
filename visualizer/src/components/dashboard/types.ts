import type { Candidate } from '../../types';
import { getEvolutionLevel } from '../../utils/evolutionLevel';

export type CandidateWithChange = Candidate & {
  changePercent: number;
  level: ReturnType<typeof getEvolutionLevel>;
};
