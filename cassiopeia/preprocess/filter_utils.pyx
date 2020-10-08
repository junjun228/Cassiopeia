"""
This file contains functions pertaining to filtering cell doublets and mapping
intBCs. Invoked through pipeline.py and supports the filter_alignments and 
call_lineage_group functions. 
"""

import os
import logging
import time
import sys

from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
from matplotlib import colors, colorbar
import numpy as np
import pandas as pd
import pylab
import scipy as sp
from scipy import cluster
from tqdm import tqdm
import yaml

from cassiopeia.preprocess import utilities

sys.setrecursionlimit(10000)


def map_intbcs(
    moleculetable: pd.DataFrame,
    verbose: bool = False
) -> pd.DataFrame:
    """Performs a procedure to cleanly assign one allele to each intBC/cellBC 
    pairing

    For each intBC/cellBC pairing, selects the most frequent allele and 
    removes alignments that don't have that allele.

    Args: 
        moleculetable: A molecule table of cellBC-UMI pairs to be filtered
        verbose: Indicates whether to log every correction and the number of
            cellBCs and UMIs remaining after filtering

    Returns
        An allele table with one allele per cellBC-intBC pair
    """

    # Have to drop out all intBCs that are NaN
    moleculetable = moleculetable.dropna(subset=["intBC"])

    # create mappings from intBC/cellBC pairs to alleles
    moleculetable["status"] = "good"
    moleculetable["filter_column"] = moleculetable[["intBC", "cellBC"]].apply(lambda x: '_'.join(x), axis=1)
    moleculetable["filter_column2"] = moleculetable[["intBC", "cellBC", "allele"]].apply(lambda x: "_".join(x), axis=1)
    moleculetable["allele_counter"] = moleculetable["allele"]

    filter_dict = {}

    # For each intBC/cellBC pair, we want only one allele (select majority allele for now)
    corrected = 0
    numUMI_corrected = 0
    for n, group in tqdm(moleculetable.groupby(["filter_column"]), desc = "Mapping intBCs"):

        x1 = group.groupby(["filter_column2", "allele"]).agg({"readCount": "sum", "allele_counter": "count", "UMI": "count"}).sort_values("readCount", ascending=False).reset_index()

        # If we've found an intBC that corresponds to more than one allele in the same cell, then let's error correct towards
        # the more frequently occuring allele

        # But, this will ALWAYS be the first allele because we sorted above, so we can generalize and always assign the intBC to the
        # first element in x1.

        a = x1.iloc[0]["allele"]

        # Let's still keep count of how many times we had to re-assign for logging purposes
        filter_dict[x1.iloc[0]["filter_column2"]] = "good"
        if x1.shape[0] > 1:

            for i in range(1, x1.shape[0]):
                filter_dict[x1.iloc[i]["filter_column2"]] = "bad"
                corrected += 1
                numUMI_corrected += x1.loc[i,"UMI"]


            if verbose:
                for i in range(1, x1.shape[0]):
                    logging.info(f"In group {n}, re-assigned allele " +  str(x1.loc[i, "allele"]) + f" to {a},"
                    + " re-assigning UMI " + str(x1.loc[i, "UMI"]) + " to " + str(x1.loc[0, "UMI"]))
                    # out_str += n + "\t" + x1.loc[i, "allele"] + "\t" + a + "\t"
                    # out_str += str(x1.loc[i, "UMI"]) + "\t" + str(x1.loc[0, "UMI"]) + "\n"

    moleculetable["status"] = moleculetable["filter_column2"].map(filter_dict)
    moleculetable = moleculetable[(moleculetable["status"] == "good")]
    moleculetable.index = [i for i in range(moleculetable.shape[0])]
    moleculetable = moleculetable.drop(columns=["filter_column", "filter_column2", "allele_counter", "status"])

    # log results
    if verbose:
        logging.info("Picking alleles:")
        logging.info(f"# Alleles removed: {corrected}")
        logging.info(f"# UMIs affected through removing alleles: {numUMI_corrected}")
        utilities.generate_log_output(moleculetable)

    return moleculetable

def filter_intra_doublets(
    molecule_table: pd.DataFrame, 
    prop: float = 0.1, 
    verbose: bool = False
) -> pd.DataFrame:
    """Filters a DataFrame for doublet cells that present too much conflicting
    allele information within a clonal population.

    For each cellBC, calculates the most common allele for each intBC by UMI 
    count. Also calculates the proportion of UMIs of alleles that conflict
    with the most common. If the proportion across all UMIs is > prop, filters
    out alignments with that cellBC from the DataFrame.

    Args: 
        moleculetable: A molecule table of cellBC-UMI pairs to be filtered
        prop: A threshold representing the minimum proportion of conflicting
        UMIs needed to filter out a cellBC from the DataFrame
        verbose: Indicates whether to log the number of doublets filtered out
        of the total number of cells

    Returns
        A filtered molecule table
    """

    doublet_list = []
    filter_dict = {}
    for n, g in tqdm(molecule_table.groupby(["cellBC"])):
        x = g.groupby(["intBC", "allele"]).agg({"UMI": "count"}).sort_values("UMI", ascending=False).reset_index()
        xuniq = x.drop_duplicates(subset=["intBC"], keep = "first")

        conflicting_umi_count = x["UMI"].sum() - xuniq["UMI"].sum()
                    
        prop_multi_alleles = conflicting_umi_count / x["UMI"].sum()

        if prop_multi_alleles > prop:
            filter_dict[n] = "bad"
        else:
            filter_dict[n] = "good"

    molecule_table["status"] = molecule_table["cellBC"].map(filter_dict)

    doublet_list = molecule_table[(molecule_table["status"] == "bad")]["cellBC"].unique()

    if verbose: 
        logging.info(f"Filtered {len(doublet_list)} Intra-Lineage Group Doublets of " + str(len(molecule_table["cellBC"].unique())))

    molecule_table = molecule_table[(molecule_table["status"] == "good")]
    molecule_table = molecule_table.drop(columns = ["status"])

    if verbose:
        utilities.generate_log_output(molecule_table)

    return molecule_table


def get_intbc_sets(
    lgs: List[pd.DataFrame], 
    lg_names: List[int], 
    thresh: int = None
) -> Tuple[Dict[int, List[str]], Dict[int, pd.DataFrame]]:
    """A simple function to return the intBC sets of each lineage group.

    Given a list of lineage groups, returns the intBC set for that lineage 
    group, i.e. the set of intBCs that the cells in the lineage group have.
    If thresh is specified, also filters out intBCs with low proportions.

    Args:
        lgs: A list of allele tables, one representing each lineage group
        lg_names: A list of lineage group names
        thresh: The minimum proportion of cells that have an intBC in each 
            lineage group in order for that intBC to be included in the intBC 
            set

    Returns:
        A dictionary of the intBC sets of each lineage group and a dictionary 
        of the cell proportion of cells that do not have that intBC for each 
        lineage group
    """

    intbc_sets = {}
    dropouts = {}

    for n, g in zip(lg_names, lgs):
        piv = pd.pivot_table(g, index="cellBC", columns="intBC", values="UMI", aggfunc=pylab.size)
        do = piv.apply(lambda x: x.isnull().sum() / float(piv.shape[0]), axis=0)

        if thresh is None:

            intbc_sets[n] = do.index
            dropouts[n] = do

        else:
            # Filter all intBCs whose cell proportion is < thresh
            intbcs = do[do < thresh].index
            intbc_sets[n] = intbcs
            dropouts[n] = do

    return intbc_sets, dropouts


def compute_lg_membership(
    cell: pd.DataFrame,
    intbc_sets: Dict[int, List[str]], 
    lg_dropouts: Dict[int, pd.DataFrame]
) -> Dict[int, float]:
    """Calculates the kinship for the given cell for each lineage group.

    Given a cell, for each lineage group, it calculates the intBC intersection
    with that lineage group, weighted by the cell proportions that have each
    intBC in that group. 

    Args:
        cell: An allele table subsetted to one cellBC
        intbc_sets: A dictionary of the intBC sets of each lineage group
        lg_dropouts: A dictionary of the cell proportion of cells that do not 
            have that intBC for each lineage group
    Returns:
        A kinship score for each lineage group
    """
    
    lg_mem = {}

    # Get the intBC set for the cell
    ibcs = np.unique(cell["intBC"])

    for i in intbc_sets.keys():

        lg_do = lg_dropouts[i]
        # Calculate the intersect
        intersect = np.intersect1d(ibcs, intbc_sets[i])
        if len(intersect) > 0:
            # Calculate weighted intersection, normalized by the total cell proportions
            lg_mem[i] = np.sum(1 - lg_do[intersect]) / np.sum(1 - lg_do)

        else:
            lg_mem[i] = 0

    # Normalize the membership values across linaege groups
    factor = 1.0 / np.sum(list(lg_mem.values()))
    for l in lg_mem:
        lg_mem[l] = lg_mem[l] * factor

    return lg_mem


def filter_inter_doublets(
    at: pd.DataFrame, 
    rule: float = 0.35, 
    verbose: bool = False
) -> pd.DataFrame:
    """Filters out cells whose kinship with their assigned lineage is low.
    Essentially, filters out cells that have ambigious kinship across multiple
    lineage groups. 

    For every cell, calculates the kinship it has with its assigned lineage,
    with kinship defined as the weighted proportion of intBCs it shares with
    the intBC set for a lineage (see compute_lg_membership for more details
    on the weighting). If that kinship is <= rule, then it is filtered out.

    Args:
        at: An allele table of cellBC-intBC-allele groups to be filtered
        rule: The minimum kinship threshold which a cell needs to pass in order
            to be included in the final DataFrame
        verbose: Indicates whether to log the number of filtered cells
    Returns:
        A filtered allele table
    """

    def filter_cell(cell, rule):
        true_lg = cell.loc["LG"]
        return float(cell.loc[true_lg]) < rule

    collapsed_lgs = []
    lg_names = list(at["lineageGrp"].unique())

    for n in lg_names:
        collapsed_lgs.append(at[at["lineageGrp"] == n])

    ibc_sets, dropouts = get_intbc_sets(collapsed_lgs, lg_names)

    # Calculate kinship for each lineage group for each cell
    mems = {}
    for n, g in at.groupby("cellBC"):
        lg = int(g["lineageGrp"].iloc[0])
        mem = compute_lg_membership(g, ibc_sets, dropouts)
        mem["LG"] = lg
        mems[n] = mem

    mem_df = pd.DataFrame.from_dict(mems).T

    filter_dict = {}

    for cell in tqdm(mem_df.index, desc="Identifying inter-doublets"):
        if filter_cell(mem_df.loc[cell], rule):
            filter_dict[cell] = "bad"
        else:
            filter_dict[cell] = "good"

    at["status"] = at["cellBC"].map(filter_dict)
    at_n = at[at["status"] == "good"]

    dl = len(at[at["status"] == "bad"]["cellBC"].unique())
    tot = len(at["cellBC"].unique())

    if verbose:
        logging.info(f"Filtered {dl} inter-doublets of {tot} cells") 

    return at_n.drop(columns=["status"])
