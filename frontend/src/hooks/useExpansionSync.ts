import { useState, useCallback } from 'react';

export interface ExpansionSyncState {
  // Visible counts for middle view and tree
  visibleTpCount: number;
  visibleSeedCount: number;
  visibleCharCount: number;
  visibleVolumeCount: number;

  // Show all flags
  showAllTps: boolean;
  showAllSeeds: boolean;
  showAllChars: boolean;
  showAllVolumes: boolean;

  // Sub-tree branch accordion toggles
  expandWorldview: boolean;
  expandTps: boolean;
  expandSeeds: boolean;
  expandChars: boolean;
  expandVols: boolean;
  expandedVolumeIndices: number[];

  // Mutators and sync actions
  setVisibleTpCount: React.Dispatch<React.SetStateAction<number>>;
  setVisibleSeedCount: React.Dispatch<React.SetStateAction<number>>;
  setVisibleCharCount: React.Dispatch<React.SetStateAction<number>>;
  setVisibleVolumeCount: React.Dispatch<React.SetStateAction<number>>;

  setShowAllTps: React.Dispatch<React.SetStateAction<boolean>>;
  setShowAllSeeds: React.Dispatch<React.SetStateAction<boolean>>;
  setShowAllChars: React.Dispatch<React.SetStateAction<boolean>>;
  setShowAllVolumes: React.Dispatch<React.SetStateAction<boolean>>;

  setExpandWorldview: React.Dispatch<React.SetStateAction<boolean>>;
  setExpandTps: React.Dispatch<React.SetStateAction<boolean>>;
  setExpandSeeds: React.Dispatch<React.SetStateAction<boolean>>;
  setExpandChars: React.Dispatch<React.SetStateAction<boolean>>;
  setExpandVols: React.Dispatch<React.SetStateAction<boolean>>;
  setExpandedVolumeIndices: React.Dispatch<React.SetStateAction<number[]>>;

  // Two-way synchronization methods
  syncTpCount: (count: number) => void;
  syncSeedCount: (count: number) => void;
  syncCharCount: (count: number) => void;
  syncVolumeCount: (count: number) => void;

  toggleShowAllTps: (totalCount?: number) => void;
  toggleShowAllSeeds: (totalCount?: number) => void;
  toggleShowAllChars: (totalCount?: number) => void;
  toggleShowAllVolumes: (totalCount?: number) => void;

  toggleVolumeChaptersExpand: (vIdx: number) => void;
}

export const useExpansionSync = (): ExpansionSyncState => {
  // Counts currently visible/rendered
  const [visibleTpCount, setVisibleTpCount] = useState<number>(8);
  const [visibleSeedCount, setVisibleSeedCount] = useState<number>(8);
  const [visibleCharCount, setVisibleCharCount] = useState<number>(8);
  const [visibleVolumeCount, setVisibleVolumeCount] = useState<number>(4);

  // Show-all toggles
  const [showAllTps, setShowAllTps] = useState<boolean>(false);
  const [showAllSeeds, setShowAllSeeds] = useState<boolean>(false);
  const [showAllChars, setShowAllChars] = useState<boolean>(false);
  const [showAllVolumes, setShowAllVolumes] = useState<boolean>(false);

  // Accordion branch expansions in tree
  const [expandWorldview, setExpandWorldview] = useState<boolean>(true);
  const [expandTps, setExpandTps] = useState<boolean>(true);
  const [expandSeeds, setExpandSeeds] = useState<boolean>(false);
  const [expandChars, setExpandChars] = useState<boolean>(true);
  const [expandVols, setExpandVols] = useState<boolean>(true);
  const [expandedVolumeIndices, setExpandedVolumeIndices] = useState<number[]>([]);

  // Called whenever middle view loads more items via scroll or button
  const syncTpCount = useCallback((count: number) => {
    setVisibleTpCount((prev) => {
      const nextCount = Math.max(prev, count);
      if (nextCount > 15) {
        setShowAllTps(true);
      }
      return nextCount;
    });
    setExpandTps(true);
  }, []);

  const syncSeedCount = useCallback((count: number) => {
    setVisibleSeedCount((prev) => {
      const nextCount = Math.max(prev, count);
      if (nextCount > 15) {
        setShowAllSeeds(true);
      }
      return nextCount;
    });
    setExpandSeeds(true);
  }, []);

  const syncCharCount = useCallback((count: number) => {
    setVisibleCharCount((prev) => {
      const nextCount = Math.max(prev, count);
      if (nextCount > 12) {
        setShowAllChars(true);
      }
      return nextCount;
    });
    setExpandChars(true);
  }, []);

  const syncVolumeCount = useCallback((count: number) => {
    setVisibleVolumeCount((prev) => Math.max(prev, count));
    setExpandVols(true);
  }, []);

  // Called when tree or middle clicks "展開全部" / "收合"
  const toggleShowAllTps = useCallback((totalCount?: number) => {
    setShowAllTps((prev) => {
      const next = !prev;
      if (next && totalCount) {
        setVisibleTpCount(totalCount);
      }
      return next;
    });
    setExpandTps(true);
  }, []);

  const toggleShowAllSeeds = useCallback((totalCount?: number) => {
    setShowAllSeeds((prev) => {
      const next = !prev;
      if (next && totalCount) {
        setVisibleSeedCount(totalCount);
      }
      return next;
    });
    setExpandSeeds(true);
  }, []);

  const toggleShowAllChars = useCallback((totalCount?: number) => {
    setShowAllChars((prev) => {
      const next = !prev;
      if (next && totalCount) {
        setVisibleCharCount(totalCount);
      }
      return next;
    });
    setExpandChars(true);
  }, []);

  const toggleShowAllVolumes = useCallback((totalCount?: number) => {
    setShowAllVolumes((prev) => {
      const next = !prev;
      if (next && totalCount) {
        setVisibleVolumeCount(totalCount);
      }
      return next;
    });
    setExpandVols(true);
  }, []);

  const toggleVolumeChaptersExpand = useCallback((vIdx: number) => {
    setExpandedVolumeIndices((prev) =>
      prev.includes(vIdx) ? prev.filter((i) => i !== vIdx) : [...prev, vIdx]
    );
  }, []);

  return {
    visibleTpCount,
    visibleSeedCount,
    visibleCharCount,
    visibleVolumeCount,
    showAllTps,
    showAllSeeds,
    showAllChars,
    showAllVolumes,
    expandWorldview,
    expandTps,
    expandSeeds,
    expandChars,
    expandVols,
    expandedVolumeIndices,

    setVisibleTpCount,
    setVisibleSeedCount,
    setVisibleCharCount,
    setVisibleVolumeCount,
    setShowAllTps,
    setShowAllSeeds,
    setShowAllChars,
    setShowAllVolumes,
    setExpandWorldview,
    setExpandTps,
    setExpandSeeds,
    setExpandChars,
    setExpandVols,
    setExpandedVolumeIndices,

    syncTpCount,
    syncSeedCount,
    syncCharCount,
    syncVolumeCount,
    toggleShowAllTps,
    toggleShowAllSeeds,
    toggleShowAllChars,
    toggleShowAllVolumes,
    toggleVolumeChaptersExpand,
  };
};
