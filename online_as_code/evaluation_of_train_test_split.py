import copy
import logging
import numpy as np
import pandas as pd
import os
import time
from aslib_scenario.aslib_scenario import ASlibScenario
from par_10_regret_metric import Par10RegretMetric
from learner_runtime_metric import LearnerRuntimeMetric
from numpy import ndarray

logger = logging.getLogger("evaluate_train_test_split")
logger.addHandler(logging.StreamHandler())


def evaluate_train_test_split(scenario: ASlibScenario, approach, metrics, fold: int, amount_of_training_instances: int, censored_value_imputation:str, debug_mode:bool):

    if censored_value_imputation != 'all':
        scenario = copy.deepcopy(scenario)
        threshold = scenario.algorithm_cutoff_time
        if censored_value_imputation == 'clip_censored':
            scenario.performance_data = scenario.performance_data.clip(upper=threshold)

        elif censored_value_imputation == 'ignore_censored':
            scenario.performance_data = scenario.performance_data.replace(10*threshold, np.nan)

    # approach.initialize(len(scenario.algorithms))
    print(scenario.algorithms)
    print(fold)
    # feature_data = scenario.feature_data.to_numpy()
    # performance_data = scenario.performance_data.to_numpy()
    # feature_cost_data = scenario.feature_cost_data.to_numpy() if scenario.feature_cost_data is not None else None
    #
    # feature_data, performance_data, feature_cost_data = shuffle_in_unison(feature_data, performance_data,feature_cost_data)
    #
    # scenario.feature_data = pd.DataFrame(feature_data)
    # scenario.performance_data = pd.DataFrame(performance_data)
    # scenario.feature_cost_data = pd.DataFrame(feature_cost_data)
    approach.fit(scenario,fold, len(scenario.instances)) #def fit(self, scenario: ASlibScenario, fold: int, num_instances: int):
    approach_metric_values = np.zeros(len(metrics))

    num_counted_test_values = 0

    feature_data = scenario.feature_data.to_numpy()
    performance_data = scenario.performance_data.to_numpy()
    feature_cost_data = scenario.feature_cost_data.to_numpy() if scenario.feature_cost_data is not None else None

    # feature_data, performance_data, feature_cost_data = shuffle_in_unison(feature_data, performance_data, feature_cost_data)

    last_instance_id = amount_of_training_instances
    if amount_of_training_instances <= 0:
        last_instance_id = len(scenario.instances)


    runtimes_per_instance = list()
    cumulative_regret_per_instance = list()
    regret_per_instance = list()

    start_time = time.time()
    total_time = 0
    for instance_id in range(len(scenario.instances)*(fold-1)//10, len(scenario.instances)*(fold)//10):

        if instance_id % 100 == 0 and instance_id > 0:
            end_time = time.time()
            if debug_mode:
                logger.info("Starting with instance " + str(instance_id)+ ". Last 100 instances took " + "{:.2f}".format(end_time-start_time) + " s .")
            start_time = time.time()

        X = feature_data[instance_id]
        y = performance_data[instance_id]

        # check if instance contains a non-censored value. If not, we will ignore it, as it does not have a ground truth
        # contains_non_censored_value = False
        # for y_element in y:
        #     if y_element < scenario.algorithm_cutoff_time:
        #         contains_non_censored_value = True
        contains_non_censored_value = True
        if contains_non_censored_value:

            # compute feature time
            accumulated_feature_time = 0
            if scenario.feature_cost_data is not None and approach.get_name() != 'sbs' and approach.get_name() != 'oracle' \
                    and not approach.get_name().startswith('feature_free_epsilon_greedy') and approach.get_name() != 'online_oracle':
                feature_time = feature_cost_data[instance_id]
                accumulated_feature_time = np.sum(feature_time)
            #initialize instance cutoff as a random value between the best and the worst algorithm
            # non_censored_y_values = y[np.where(y < scenario.algorithm_cutoff_time)]
            #
            # if len(non_censored_y_values) == 0:
            #     upper_instance_cutoff_bound = scenario.algorithm_cutoff_time
            #     lower_instance_cutoff_bound = 0
            # else:
            #     upper_instance_cutoff_bound = np.max(non_censored_y_values)
            #     lower_instance_cutoff_bound = np.min(non_censored_y_values)

            #instance_cutoff = np.random.uniform(low=lower_instance_cutoff_bound, high=upper_instance_cutoff_bound)
            instance_cutoff = scenario.algorithm_cutoff_time

            instance_start_time = time.time_ns()

            #query prediction from learner
            if approach.get_name() == 'online_oracle':
                #for the online oracle we want to pass the id of the best algorithm as instance id such that it can be chosen easily
                predicted_scores = approach.predict(X, np.argmin(y), instance_cutoff)
            else:
                predicted_scores = approach.predict(X, instance_id)#, instance_cutoff   offline的predict只有两个参数
            predicted_algorithm_id = np.argmin(predicted_scores)

            #train learner with new sample
            #offline中无对应函数暂时注释
            # approach.train_with_single_instance(X, predicted_algorithm_id, y[predicted_algorithm_id], instance_cutoff)

            instance_end_time = time.time_ns()
            total_instance_time = instance_end_time - instance_start_time
            total_time = total_time + total_instance_time
            #add model time to accumulated feature time in online setting: #TODO
            #accumulated_feature_time = accumulated_feature_time + (total_instance_time /1000000000.0)

            #make sure that we plot the runtime per instance for plotting
            runtimes_per_instance.append(total_instance_time / 1000000000)

            #compute the values of the different metrics
            num_counted_test_values += 1
            for i, metric in enumerate(metrics):
                metric_result = metric.evaluate(y, predicted_scores, accumulated_feature_time, instance_cutoff)
                approach_metric_values[i] = (approach_metric_values[i] + metric_result)
                #make sure that we track the cumulative regret per instance for plotting
                if metric.get_name() == Par10RegretMetric().get_name():
                    cumulative_regret_per_instance.append(approach_metric_values[i])
                    regret_per_instance.append(metric_result)

    approach_metric_values = np.true_divide(approach_metric_values, num_counted_test_values)

    for i, metric in enumerate(metrics):
        #make sure that the regret is not averaged across instances
        if metric.get_name() == Par10RegretMetric().get_name():
            approach_metric_values[i] = approach_metric_values[i]*num_counted_test_values

        #add correct values for learner runtime as these can only be evaluated here
        if metric.get_name() == LearnerRuntimeMetric().get_name():
            approach_metric_values[i] = (total_time / num_counted_test_values) / 1000000000 #in seconds

        print(metrics[i].get_name() + ': {0:.10f}'.format(approach_metric_values[i]))


    write_plot_file(values_to_save=cumulative_regret_per_instance, file_name_prefix='cumulative_regret', scenario_name=scenario.scenario, fold = fold, approach=approach.get_name())
    write_plot_file(values_to_save=regret_per_instance, file_name_prefix='regret', scenario_name=scenario.scenario, fold = fold, approach=approach.get_name())
    write_plot_file(values_to_save=runtimes_per_instance, file_name_prefix='runtimes', scenario_name=scenario.scenario, fold = fold, approach=approach.get_name())

    return approach_metric_values


def write_plot_file(values_to_save: list, file_name_prefix:str, scenario_name: str, fold: int, approach: str):
    if not os.path.exists('output/' + file_name_prefix + "/"):
        os.makedirs('output/' + file_name_prefix + "/")
    complete_instance_wise_string = ';'.join(str(v) for v in values_to_save)
    f = open("output/" + file_name_prefix + "/" + scenario_name + "+" + str(fold) + "+" + approach + ".txt", "w")
    f.write(complete_instance_wise_string + "\n")
    f.close()

def shuffle_in_unison(a:ndarray , b:ndarray, c:ndarray):
    assert len(a) == len(b)
    if c is not None:
        assert len(b) == len(c)
    shuffled_a = np.empty(a.shape, dtype=a.dtype)
    shuffled_b = np.empty(b.shape, dtype=b.dtype)
    if c is not None:
        shuffled_c = np.empty(c.shape, dtype=c.dtype)
    permutation = np.random.permutation(len(a))
    for old_index, new_index in enumerate(permutation):
        shuffled_a[new_index] = a[old_index]
        shuffled_b[new_index] = b[old_index]
        if c is not None:
            shuffled_c[new_index] = c[old_index]
    if c is None:
        return shuffled_a, shuffled_b, c
    return shuffled_a, shuffled_b, shuffled_c