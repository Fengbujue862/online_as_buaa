import configparser
import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np
from sqlalchemy import create_engine, text
import seaborn as sns
import matplotlib.pyplot as plt
import re
import os
from analysis_utility import load_configuration
from analysis_utility import clean_algorithm_name
from analysis_utility import create_directory_if_not_exists
from scipy.stats import median_absolute_deviation

def bold_extreme_values(data, best=-1, second_best=-1, decimal_places:int  = 2):
    if data == best:
        return "\\textbf{%s}" % format_number(data, decimal_places=decimal_places)

    if data == second_best:
        return "\\underline{%s}" % format_number(data, decimal_places=decimal_places)

    return format_number(data, decimal_places=decimal_places)

def format_number(data, decimal_places: int = 2, maximum_length_before_comma: int = 6):
    format_string = ("{:." + str(decimal_places) + "f}")
    format_string_scientific_notation = ("{:." + str(decimal_places) + "e}")
    formated_string = format_string.format(data)
    if len(formated_string) > maximum_length_before_comma  + decimal_places:
        formated_string = format_string_scientific_notation.format(data)
    return formated_string


def generate_improvement_over_sbs_barchart(sql_query:str):
    df = generate_npar10_dataframe(sql_query)

    #make sure that the Degroote variants are at the end and Thompson first
    df.columns = (df.columns.to_series()
                  .apply(lambda r: 'z_' + r if r.lower().startswith('degroo') else r))
    df.columns = (df.columns.to_series()
                  .apply(lambda r: 'aa_' + r if 'thompson' in r.lower() else r))
    df = df.reindex(sorted(df.columns), axis=1)
    df.columns = (df.columns.to_series()
                  .apply(lambda r: r.replace('z_', '') if r.lower().startswith('z_') else r))
    df.columns = (df.columns.to_series()
                  .apply(lambda r: r.replace('aa_', '') if r.lower().startswith('aa_') else r))


    number_of_scenarios_better_than_sbs= df[df < 1].count()
    total_number_of_scenarios = df.count()
    number_of_scenarios_equal_or_worse_than_sbs = total_number_of_scenarios - number_of_scenarios_better_than_sbs

    categories = ['improvement','no improvement']

    labels = df.columns.to_numpy()
    labels = np.array([clean_algorithm_name(label) for label in labels])

    plt.bar(x = labels, height=number_of_scenarios_better_than_sbs, color='forestgreen')
    plt.bar(x = labels, height=number_of_scenarios_equal_or_worse_than_sbs, bottom=number_of_scenarios_better_than_sbs, color='grey')

    plt.xlabel('Approaches')
    plt.ylabel('Number of scenarios')
    plt.title('(No) Improvement over SBS')
    plt.legend(categories)
    plt.tight_layout()

    figure_directory = 'figures'
    create_directory_if_not_exists(figure_directory)

    plt.savefig(figure_directory + '/sbs_improvement_plot.pdf')

def generate_result_table(sql_query:str, npar10:bool = False, stddev: bool = False, decimal_places: int = 2, show_avg_and_median: bool = True):
    if npar10:
        df = generate_npar10_dataframe(sql_query)
    else:
        dataframe = get_dataframe_for_sql_query(sql_query)
        df = dataframe.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')
    df_rank= df.rank(axis=1)
    if show_avg_and_median:
        df_avg = df.mean()
        df_median = df.median()

    for k in range(len(df.index)):
        df.iloc[k] = df.iloc[k].apply(
            lambda data: bold_extreme_values(data, best=df.iloc[k].min(), second_best=np.partition(df.iloc[k].array.to_numpy(), 1)[1], decimal_places=decimal_places))

    if stddev:
        if npar10:
            raise Exception("Cannot use npar10 and stddev option jointly.")
        stddev_df = get_dataframe_for_sql_query(sql_query)
        stddev_df = stddev_df.pivot_table(values='stddev_result', index='scenario_name', columns='approach', aggfunc='first')
        for k in range(len(stddev_df.index)):
            stddev_df.iloc[k] = stddev_df.iloc[k].apply(
                lambda data: format_number(data, decimal_places=decimal_places))

        df = df.astype(str) + " $\\pm$ " + stddev_df.astype(str)

    if show_avg_and_median:
        if not df.empty:
            df.loc['avg'] = df_avg
            df.loc['median'] = df_median
    if not df.empty:
        df.loc['avgrank'] =  df_rank.mean()

    #make sure that the Degroote variants are at the end and Thompson first
    df.columns = (df.columns.to_series()
                  .apply(lambda r: 'z_' + r if r.lower().startswith('degroo') else r))
    df.columns = (df.columns.to_series()
                  .apply(lambda r: 'aa_' + r if 'thompson' in r.lower() else r))
    df = df.reindex(sorted(df.columns), axis=1)
    df.columns = (df.columns.to_series()
                  .apply(lambda r: r.replace('z_', '') if r.lower().startswith('z_') else r))
    df.columns = (df.columns.to_series()
                  .apply(lambda r: r.replace('aa_', '') if r.lower().startswith('aa_') else r))

    # Set column header to bold title case
    df.columns = (df.columns.to_series()
                  .apply(lambda r:
                         '\\multicolumn{1}{c}{\\rotatebox{90}{' + clean_algorithm_name(r).replace('_', '\_') + '}}'))

    print(df.to_latex(index=True, escape=False).replace('approach','\\multicolumn{1}{c|}{\\rotatebox{90}{Approach}}').replace('SAT03-16_INDU','SAT03-16\\_INDU').replace('scenario_name','Scenario'))

def generate_npar10_dataframe(sql_query: str):
    online_oracle_df = get_dataframe_for_sql_query("SELECT scenario_name, approach, AVG(result) as avg_result FROM `server_results_all_variants` WHERE metric='par10' and approach = 'snnap' GROUP BY scenario_name, approach, metric ORDER BY scenario_name")
    online_oracle_df = online_oracle_df.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')
    online_oracle_series = pd.Series(online_oracle_df['snnap'], online_oracle_df.index)
    #ff_greedy_df = get_dataframe_for_sql_query("SELECT scenario_name, approach, AVG(result) as avg_result FROM `server_results_all_variants` WHERE metric='par10' and approach = 'feature_free_epsilon_greedy_cutoff' GROUP BY scenario_name, approach, metric ORDER BY scenario_name")
    #ff_greedy_df = ff_greedy_df.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')
    #ff_greedy_series = pd.Series(ff_greedy_df['feature_free_epsilon_greedy_cutoff'], ff_greedy_df.index)

    dataframe = get_dataframe_for_sql_query(sql_query)
    df = dataframe.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')


    #denominator = ff_greedy_df.sub(online_oracle_series, axis='index')
    #denominator_series = pd.Series(denominator['feature_free_epsilon_greedy_cutoff'], denominator.index)
    denominator_series = online_oracle_series

    #nominator = df.sub(online_oracle_series, axis='index')
    nominator = df

    npar10_df = (nominator).div(denominator_series, axis='index')
    return npar10_df

def generate_ablation_plots(algorithm: str):
    if algorithm == 'ucb':
        algorithm_stub = 'lin'
    if algorithm == 'thompson':
        algorithm_stub = 'thom'
    time_query = "SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result) FROM `server_results_all_variants` WHERE metric='learner_runtime_s_per_step' AND approach LIKE '%e\_%' AND  approach LIKE '%" + algorithm_stub +"%' AND approach != 'online_oracle' GROUP BY scenario_name, approach, metric ORDER BY scenario_name, avg_result"
    time_df = get_dataframe_for_sql_query(time_query)
    time_df = time_df.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')
    time_mean = time_df.mean()
    par10_query = "SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result) FROM `server_results_all_variants` WHERE metric='par10' AND approach LIKE '%e\_%' AND  approach LIKE '%" + algorithm_stub +"%' AND approach != 'online_oracle' GROUP BY scenario_name, approach, metric ORDER BY scenario_name, avg_result"
    npar10_df = generate_npar10_dataframe(par10_query)
    npar10_mean = npar10_df.median()

    fig, ax = plt.subplots()
    if algorithm == 'ucb':
        markers = ['2', 'H', '.', 'v', '*', '+','^', 'X']
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#e377c2', '#9467bd', '#8c564b', '#7f7f7f', '#bcbd22', '#17becf']
    if algorithm == 'thompson':
        markers = ['o', '1', 'p', 'P']
        colors = ['#1f77b4', '#ff7f0e', '#e377c2', '#d62728']
    for i,name in enumerate(npar10_mean.index):
        short_name = clean_algorithm_name(name)
        ax.scatter(x=time_mean.loc[name], y=npar10_mean.loc[name], label=short_name, marker=markers[i], c=colors[i], s=120)
    ax.legend()
    plt.ylabel('rePAR10')
    plt.xlabel('avg. prediction time in seconds')

    figure_directory = 'figures'
    create_directory_if_not_exists(figure_directory)

    plt.tight_layout()
    plt.savefig(figure_directory + '/ablation_' + algorithm + '.pdf')

def generate_competitor_plots():
    placeholder = 'PLACEHOLDER'
    query = "SELECT * FROM ((SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result) FROM `server_results_all_variants` WHERE metric='" + placeholder + "' AND approach LIKE '%e\_%' AND  (approach LIKE 'bj_e_thompson_s%' OR approach LIKE 'e_thompson_rev%' OR approach LIKE 'e_rand_blinducb_s%' OR approach LIKE 'e_bclinucb_rev_s%') AND approach != 'online_oracle' GROUP BY scenario_name, approach, metric) UNION ALL (SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result) FROM `server_results_all_variants` WHERE metric='" + placeholder + "' AND approach='degroote_EpsilonGreedy_LinearRegression' GROUP BY scenario_name, approach, metric)) as B ORDER BY scenario_name, avg_result"
    time_query = query.replace(placeholder, 'learner_runtime_s_per_step')
    time_df = get_dataframe_for_sql_query(time_query)
    time_df = time_df.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')
    time_mean = time_df.mean()
    par10_query = query.replace(placeholder, 'par10')
    npar10_df = generate_npar10_dataframe(par10_query)
    npar10_mean = npar10_df.median()

    fig, ax = plt.subplots()
    markers=['1', 'x', '2', 'X', 'p']
    colors = ['#ff7f0e', '#17becf', '#1f77b4', '#7f7f7f', '#e377c2']
    for i,name in enumerate(npar10_mean.index):
        short_name = clean_algorithm_name(name)
        ax.scatter(x=time_mean.loc[name], y=npar10_mean.loc[name], label=short_name, marker=markers[i], c=colors[i], s=120)
    ax.legend()
    plt.ylabel('rePAR10')
    plt.xlabel('avg. prediction time in seconds')

    figure_directory = 'figures'
    create_directory_if_not_exists(figure_directory)

    plt.tight_layout()
    plt.savefig(figure_directory + '/competitor_plot.pdf')


def get_dataframe_for_sql_query(sql_query: str):
    db_credentials = get_database_credential_string()
    return pd.read_sql(text(sql_query), con=db_credentials)

def get_database_credential_string():
    config = load_configuration()
    db_config_section = config['DATABASE']
    db_host = db_config_section['host']
    db_username = db_config_section['username']
    db_password = db_config_section['password']
    db_database = db_config_section['database']
    return "mysql://" + db_username + ":" + db_password + "@" + db_host + "/" + db_database

def generate_preliminary_result_table():
    dataframe = get_dataframe_for_sql_query("SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result) FROM `server_results_standard_all_v2` WHERE metric='par10' GROUP BY scenario_name, approach, metric ORDER BY scenario_name, avg_result")
    dataframe = dataframe.pivot_table(values='avg_result', index='scenario_name', columns='approach', aggfunc='first')
    print(dataframe.to_latex(index=False, float_format="%.3f"))


#generate_improvement_over_sbs_barchart("SELECT * FROM ((SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result) FROM `server_results_all_variants` WHERE metric='par10' AND approach LIKE '%e\_%' AND  (approach LIKE 'e_thompson_s%' OR approach LIKE 'bj_e_thompson_rev%' OR approach LIKE 'e_rand_bclinucb_s%' OR approach LIKE 'e_rand_blinducb_s%') AND approach != 'online_oracle' GROUP BY scenario_name, approach, metric)) as B ORDER BY scenario_name, avg_result")

generate_ablation_plots('ucb')
print('Successfully generated ablation plots for UCB.')
generate_ablation_plots('thompson')
print('Successfully generated ablation plots for Thompson.')
generate_competitor_plots()
print('Successfully generated competitor plots.')

# result table for our stuff
print("Small result table in main paper")
generate_result_table("SELECT * FROM ((SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result), STDDEV(result) as stddev_result FROM `server_results_all_variants` WHERE metric='par10' AND (approach LIKE 'e_thompson_rev%' OR approach LIKE 'bj_e_thompson_s%') AND approach != 'online_oracle' AND approach != 'feature_free_epsilon_greedy_cutoff' GROUP BY scenario_name, approach, metric) UNION ALL (SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result), STDDEV(result) as stddev_result FROM `server_results_all_variants` WHERE metric='par10' AND approach='degroote_EpsilonGreedy_LinearRegression' GROUP BY scenario_name, approach, metric)) as B ORDER BY scenario_name", npar10=False, stddev=True, show_avg_and_median = False)

# result table for all stuff
print("Result table for all approaches in appendix")
generate_result_table("SELECT * FROM ((SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result), STDDEV(result) as stddev_result FROM `server_results_all_variants` WHERE metric='par10' AND approach LIKE '%e\_%' AND approach != 'online_oracle' AND approach != 'feature_free_epsilon_greedy_cutoff' GROUP BY scenario_name, approach, metric) UNION ALL (SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result), STDDEV(result) as stddev_result FROM `server_results_all_variants` WHERE metric='par10' AND approach='degroote_EpsilonGreedy_LinearRegression' GROUP BY scenario_name, approach, metric)) as B ORDER BY scenario_name", npar10=False, stddev=True, show_avg_and_median = False)

#prediction time table for all stuff
print("Prediction time table")
generate_result_table("SELECT * FROM ((SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result), STDDEV(result) as stddev_result FROM `server_results_all_variants` WHERE metric='learner_runtime_s_per_step' AND approach LIKE '%e\_%' AND approach != 'online_oracle' AND approach != 'feature_free_epsilon_greedy_cutoff' GROUP BY scenario_name, approach, metric) UNION ALL (SELECT scenario_name, approach, metric, AVG(result) as avg_result, COUNT(result), STDDEV(result) as stddev_result FROM `server_results_all_variants` WHERE metric='learner_runtime_s_per_step' AND approach='degroote_EpsilonGreedy_LinearRegression' GROUP BY scenario_name, approach, metric)) as B ORDER BY scenario_name", npar10=False, stddev=True, decimal_places=3, show_avg_and_median = True)