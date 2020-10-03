"""
This file contains all high-level functionality for preprocessing sequencing
data into character matrices ready for phylogenetic inference. This file
is mainly invoked by cassiopeia_preprocess.py.
TODO: richardyz98: Standardize logging outputs across all modules
"""

import os
import time

from typing import List, Optional, Tuple

from Bio import SeqIO
from functools import partial
import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from skbio import alignment

from pathlib import Path
from tqdm.auto import tqdm

from cassiopeia.preprocess import alignment_utilities
from cassiopeia.preprocess import constants
from cassiopeia.preprocess import UMI_utils
from cassiopeia.preprocess import utilities

DNA_SUBSTITUTION_MATRIX = constants.DNA_SUBSTITUTION_MATRIX
progress = tqdm


def resolve_umi_sequence(
    molecule_table: pd.DataFrame,
    output_directory: str,
    min_avg_reads_per_umi: float = 2.0,
    min_umi_per_cell: int = 10,
    plot: bool = True,
) -> pd.DataFrame:
    """Resolve a consensus sequence for each UMI.

    This procedure will perform UMI and cellBC filtering on the basis of reads per
    UMI and UMIs per cell and then assign the most abundant sequence to each UMI
    if there is a set of conflicting sequences per UMI.

    Args:
      molecule_table: MoleculeTable to resolve
      output_directory: Directory to store results
      min_avg_reads_per_umi: Minimum covarage (i.e. average reads) per UMI allowed
      min_umi_per_cell: Minimum number of UMIs per cell allowed

    Return:
      A MoleculeTable with unique mappings between cellBC-UMI pairs.
    """

    logging.info("Resolving UMI sequences...")

    t0 = time.time()

    if plot:
        # -------------------- Plot # of sequences per UMI -------------------- #
        equivClass_group = (
            molecule_table.groupby(["cellBC", "UMI"])
            .agg({"grpFlag": "count"})
            .sort_values("grpFlag", ascending=False)
            .reset_index()
        )

        _ = plt.figure(figsize=(8, 5))
        plt.hist(
            equivClass_group["grpFlag"],
            bins=range(1, equivClass_group["grpFlag"].max()),
        )
        plt.title("Unique Seqs per cellBC+UMI")
        plt.yscale("log", basey=10)
        plt.xlabel("Number of Unique Seqs")
        plt.ylabel("Count (Log)")
        plt.savefig(os.path.join(output_directory, "seqs_per_equivClass.png"))

    # ----------------- Select most abundant sequence ------------------ #

    mt_filter = {}
    total_numReads = {}
    top_reads = {}
    second_reads = {}
    first_reads = {}

    for _, group in tqdm(molecule_table.groupby(["cellBC", "UMI"])):

        # base case - only one sequence
        if group.shape[0] == 1:
            good_readName = group["readName"].iloc[0]
            mt_filter[good_readName] = False
            total_numReads[good_readName] = group["readCount"]
            top_reads[good_readName] = group["readCount"]

        # more commonly - many sequences for a given UMI
        else:
            group_sort = group.sort_values(
                "readCount", ascending=False
            ).reset_index()
            good_readName = group_sort["readName"].iloc[0]

            # keep the first entry (highest readCount)
            mt_filter[good_readName] = False

            total_numReads[good_readName] = group_sort["readCount"].sum()
            top_reads[good_readName] = group_sort["readCount"].iloc[0]
            second_reads[good_readName] = group_sort["readCount"].iloc[1]
            first_reads[good_readName] = group_sort["readCount"].iloc[0]

            # mark remaining UMIs for filtering
            for i in range(1, group.shape[0]):
                bad_readName = group_sort["readName"].iloc[i]
                mt_filter[bad_readName] = True

    # apply the filter using the hash table created above
    molecule_table["filter"] = molecule_table["readName"].map(mt_filter)
    n_filtered = molecule_table[molecule_table["filter"] == True].shape[0]

    logging.info(f"Filtered out {n_filtered} reads.")

    # filter based on status & reindex
    filt_molecule_table = molecule_table[
        molecule_table["filter"] == False
    ].copy()
    filt_molecule_table.drop(columns=["filter"], inplace=True)

    logging.info(f"Finished resolving UMI sequences in {time.time() - t0}s.")

    if plot:
        # ---------------- Plot Diagnositics after Resolving ---------------- #
        h = plt.figure(figsize=(14, 10))
        plt.plot(top_reads.values(), total_numReads.values(), "r.")
        plt.ylabel("Total Reads")
        plt.xlabel("Number Reads for Picked Sequence")
        plt.title("Total vs. Top Reads for Picked Sequence")
        plt.savefig(
            os.path.join(output_directory, "/total_vs_top_reads_pickSeq.png")
        )
        plt.close()

        h = plt.figure(figsize=(14, 10))
        plt.plot(first_reads.values(), second_reads.values(), "r.")
        plt.ylabel("Number Reads for Second Best Sequence")
        plt.xlabel("Number Reads for Picked Sequence")
        plt.title("Second Best vs. Top Reads for Picked Sequence")
        plt.savefig(
            os.path.join(output_directory + "/second_vs_top_reads_pickSeq.png")
        )
        plt.close()

    filt_molecule_table = utilities.filter_cells(
        filt_molecule_table, min_umi_per_cell, min_avg_reads_per_umi
    )
    return filt_molecule_table


def collapse_umis(
    out_dir: str,
    bam_fp: str,
    max_hq_mismatches: int = 3,
    max_indels: int = 2,
    n_threads: int = 1,
    show_progress: bool = True,
    force_sort: bool = True,
) -> pd.DataFrame:
    """Collapses close UMIs together from a bam file.

    On a basic level, it aggregates together identical or close reads to count
    how many times a UMI was read. Performs basic error correction, allowing
    UMIs to be collapsed together which differ by at most a certain number of
    high quality mismatches and indels in the sequence read itself. Writes out
    a dataframe of the collapsed UMIs table.

    Args:
        out_dir: The output directory where the sorted bam directory, the
          collapsed bam directory, and the final collapsed table are written to.
        bam_file_name: File path of the bam_file. Just the bam file name can be
          specified if the bam already exists in the output directory.
        max_hq_mismatches: A threshold specifying the max number of high quality
          mismatches between the seqeunces of 2 aligned segments to be collapsed.
        max_indels: A threshold specifying the maximum number of differing indels
          allowed between the sequences of 2 aligned segments to be collapsed.
        n_threads: Number of threads used. Currently only supports single
          threaded use.
        show_progress: Allow progress bar to be shown.
        force_sort: Specify whether to sort the initial bam directory, regardless
          of if the sorted file already exists.

    Returns:
        None; output table is written to file.
    """

    logging.info("Collapsing UMI sequences...")

    t0 = time.time()

    # pathing written such that the bam file that is being converted does not
    # have to exist currently in the output directory
    if out_dir[-1] == "/":
        out_dir = out_dir[:-1]
    sorted_file_name = Path(
        out_dir
        + "/"
        + ".".join(bam_fp.split("/")[-1].split(".")[:-1])
        + "_sorted.bam"
    )

    if force_sort or not sorted_file_name.exists():
        max_read_length, total_reads_out = UMI_utils.sort_cellranger_bam(
            bam_fp, str(sorted_file_name), show_progress=show_progress
        )
        logging.info("Sorted bam directory saved to " + str(sorted_file_name))
        logging.info("Max read length of " + str(max_read_length))
        logging.info("Total reads: " + str(total_reads_out))

    collapsed_file_name = sorted_file_name.with_suffix(".collapsed.bam")
    if not collapsed_file_name.exists():
        UMI_utils.form_collapsed_clusters(
            str(sorted_file_name),
            max_hq_mismatches,
            max_indels,
            show_progress=show_progress,
        )

    logging.info(f"Finished collapsing UMI sequences in {time.time() - t0} s.")
    collapsed_df_file_name = sorted_file_name.with_suffix(".collapsed.txt")

    df = utilities.convert_bam_to_df(
        str(collapsed_file_name), str(collapsed_df_file_name), create_pd=True,
    )
    logging.info("Collapsed bam directory saved to " + str(collapsed_file_name))
    logging.info("Converted dataframe saved to " + str(collapsed_df_file_name))
    
    return df


def align_sequences(
    queries: pd.DataFrame,
    ref_filepath: Optional[str] = None,
    ref: Optional[str] = None,
    gap_open_penalty: float = 20,
    gap_extend_penalty: float = 1,
) -> pd.DataFrame:
    """Align reads to the TargetSite refernece.

    Take in several queries store in a DataFrame mapping cellBC-UMIs to a
    sequence of interest and align each to a reference sequence. The alignment
    algorithm used is the Smith-Waterman local alignment algorithm. The desired
    output consists of the best alignment score and the CIGAR string storing the
    indel locations in the query sequence.

    TODO(mattjones315): Parallelize?

    Args:
        queries: Dataframe storing a list of sequences to align.
        ref_filepath: Filepath to the reference FASTA.
        ref: Reference sequence.
        gapopen: Gap open penalty
        gapextend: Gap extension penalty

    Returns:
        A dataframe mapping each sequence name to the CIGAR string, quality,
        and original query sequence.
    """

    assert ref or ref_filepath

    alignment_dictionary = {}

    if ref_filepath:
        ref = str(list(SeqIO.parse(ref_filepath, "fasta"))[0].seq)

    logging.info("Beginning alignment to reference...")
    t0 = time.time()

    for umi in queries.index:

        query = queries.loc[umi]

        aligner = alignment.StripedSmithWaterman(
            query.seq,
            substitution_matrix=DNA_SUBSTITUTION_MATRIX,
            gap_open_penalty=gap_open_penalty,
            gap_extend_penalty=gap_extend_penalty,
        )
        aln = aligner(ref)
        alignment_dictionary[query.readName] = (
            query.cellBC,
            query.UMI,
            query.readCount,
            aln.cigar,
            aln.query_begin,
            aln.target_begin,
            aln.optimal_alignment_score,
            aln.query_sequence,
        )

    final_time = time.time()

    logging.info(f"Finished aligning in {final_time - t0}.")
    logging.info(
        f"Average time to align each sequence: {(final_time - t0) / queries.shape[0]})"
    )

    alignment_df = pd.DataFrame.from_dict(alignment_dictionary, orient="index")
    alignment_df.columns = [
        "cellBC",
        "UMI",
        "ReadCount",
        "CIGAR",
        "QueryBegin",
        "ReferenceBegin",
        "AlignmentScore",
        "Seq",
    ]

    alignment_df.index.name = "readName"
    alignment_df.reset_index(inplace=True)

    return alignment_df

def error_correct_umis(
    input_df: pd.DataFrame,
    _id: str,
    max_UMI_distance: int = 2,
    show_progress: bool = False,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Within cellBC-intBC pairs, collapses UMIs that have close sequences.

    Error correct UMIs together within cellBC-intBC pairs. UMIs that have a
    Hamming Distance between their sequences less than a threshold are
    corrected towards whichever UMI is more abundant.

    Args:
        input_df: Input DataFrame of alignments.
        _id: Identification of sample.
        max_UMI_distance: Maximum Hamming distance between UMIs
            for error correction.
        show_progress: Allow a progress bar to be shown.
        verbose: Log every UMI correction.

    Returns:
        A DataFrame of error corrected UMIs.

    """

    assert (
        len(
            [
                i
                for i in input_df.groupby(["cellBC", "intBC", "UMI"]).size()
                if i > 1
            ]
        )
        == 0
    ), "Non-unique cellBC-UMI pair exists, please resolve UMIs."

    t0 = time.time()

    logging.info("Beginning error correcting UMIs...")

    sorted_df = input_df.sort_values(
        ["cellBC", "intBC", "ReadCount", "UMI"], ascending=[True, True, False, False]
    )

    if max_UMI_distance == 0:
        logging.info(
            "Distance of 0, no correction occured, all alignments returned"
        )
        return sorted_df

    num_corrected = 0
    total = 0

    alignment_df = pd.DataFrame()

    if show_progress:
        sorted_df = progress(sorted_df, total=total, desc="Collapsing")

    allele_groups = sorted_df.groupby(["cellBC", "intBC"])

    for fields, allele_group in allele_groups:
        cellBC, intBC = fields
        if verbose:
            logging.info(f"cellBC: {cellBC}, intBC: {intBC}")
        (allele_group, num_corr, tot) = UMI_utils.correct_umis_in_group(
            allele_group, _id, max_UMI_distance
        )
        num_corrected += num_corr
        total += tot

        alignment_df = alignment_df.append(allele_group, sort=True)

    final_time = time.time()

    logging.info(f"Finished error correcting UMIs in {final_time - t0}.")
    logging.info(
        f"{num_corrected} UMIs Corrected of {total}"
        + f"({round(float(num_corrected) / total, 5) * 100}%)"
    )

    alignment_df["readName"] = alignment_df.apply(
        lambda x: "_".join([x.cellBC, x.UMI, str(int(x.ReadCount))]), axis=1
    )

    alignment_df.set_index("readName", inplace=True)
    alignment_df.reset_index(inplace=True)

    return alignment_df

def call_alleles(
    alignments: pd.DataFrame,
    ref_filepath: Optional[str] = None,
    ref: Optional[str] = None,
    barcode_interval: Tuple[int, int] = (20, 34),
    cutsite_locations: List[int] = [112, 166, 220],
    cutsite_width: int = 12,
    context: bool = True,
    context_size: int = 5,
) -> pd.DataFrame:
    """Call indels from CIGAR strings.

    Given many alignments, we extract the indels by comparing the CIGAR strings
    of each alignment to the reference sequence. 

    Args:
        alignments: Alignments provided in dataframe
        ref_filepath: Filepath to the ference sequence
        ref: Nucleotide sequence of the reference
        barcode_interval: Interval in reference corresponding to the integration
            barcode
        cutsite_locations: A list of all cutsite positions in the reference
        cutsite_width: Number of nucleotides left and right of cutsite location
            that indels can appear in.
        context: Include sequence context around indels
        context_size: Number of bases to the right and left to include as
            context

    Returns:
        A dataframe mapping each sequence alignment to the called indels.
    """

    assert ref or ref_filepath

    alignment_to_indel = {}
    alignment_to_intBC = {}

    if ref_filepath:
        ref = str(list(SeqIO.parse(ref_filepath, "fasta"))[0].seq)

    logging.info("Calling indels...")
    t0 = time.time()

    for _, row in tqdm(
        alignments.iterrows(),
        total=alignments.shape[0],
        desc="Parsing CIGAR strings into indels",
    ):

        intBC, indels = alignment_utilities.parse_cigar(
            row.CIGAR,
            row.Seq,
            ref,
            row.ReferenceBegin,
            row.QueryBegin,
            barcode_interval,
            cutsite_locations,
            cutsite_width,
            context=context,
            context_size=context_size,
        )

        alignment_to_indel[row.readName] = indels
        alignment_to_intBC[row.readName] = intBC

    indel_df = pd.DataFrame.from_dict(
        alignment_to_indel,
        orient='index',
        columns = [f"r{i}" for i in range(1, len(cutsite_locations)+1)]
    )

    indel_df["allele"] = indel_df.apply(
        lambda x: "".join([str(i) for i in x.values]), axis=1
    )
    indel_df['intBC'] = indel_df.index.map(alignment_to_intBC)

    alignments.set_index("readName", inplace=True)

    alignments = alignments.join(indel_df)

    alignments.reset_index(inplace=True)

    final_time = time.time()

    logging.info(f"Finished calling alleles in {final_time - t0}s")
    return alignments
