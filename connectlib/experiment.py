import datetime
import logging
from typing import List
from typing import Optional

import substra

from connectlib.algorithms import Algo
from connectlib.dependency import Dependency
from connectlib.nodes import AggregationNode
from connectlib.nodes import TestDataNode
from connectlib.nodes import TrainDataNode
from connectlib.strategies import Strategy

logger = logging.getLogger(__name__)


def execute_experiment(
    # TODO: this is getting hard to read, we need to think of an other way to call execute_experiment.
    # This should be done when we add the algo strategy layer.
    # E.g.: create a dependencies pydantic class with three args
    client: substra.Client,
    algo: Algo,
    strategy: Strategy,
    train_data_nodes: List[TrainDataNode],
    test_data_nodes: List[TestDataNode],
    aggregation_node: AggregationNode,
    num_rounds: int,
    dependencies: Optional[Dependency] = None,
) -> substra.sdk.models.ComputePlan:
    """Run a complete experiment. This will train (on the `train_data_nodes`) and test (on the `test_data_nodes`)
    your `algo` with the specified `strategy` `n_rounds` times and return the compute plan object from the connect
    platform.

    In connectlib, operations are linked to each other statically before being submitted to substra.

    The execution of :
        * the `self.perform_round` method from the passed strategy **num_rounds** times
        * the `self.predict` methods from the passed strategy
    generate the static graph of operations.

    Each element necessary for those operations (CompositeTrainTuples, TestTuples and Algorithms)
    is registered to the connect platform thanks to the specified client.

    Finally, the compute plan is sent and executed.

    Args:
        client (substra.Client): A substra client to interact with the connect platform
        algo (Algo): The algorithm your strategy will execute (i.e. train and test on all the specified nodes)
        strategy (Strategy): The strategy by which your algorithm will be executed
        train_data_nodes (List[TrainDataNode]): List of the nodes where training on data occurs
        test_data_nodes (List[TestDataNode]): List of the nodes where testing on data occurs
        aggregation_node (AggregationNode): The aggregation node, where all the shared tasks occur
        num_rounds (int): The number of time your strategy will be executed
        dependencies (Dependency, optional): The list of public dependencies used by your algorithm. Defaults to None.

    Returns:
        [ComputePlan]: The generated compute plan
    """
    logger.info("Building the compute plan.")

    # create computation graph
    for _ in range(num_rounds):
        strategy.perform_round(
            algo=algo,
            train_data_nodes=train_data_nodes,
            aggregation_node=aggregation_node,
        )

    # TODO rename 'predict' into 'predict_and_score' ? the outputs are metrics here
    strategy.predict(
        algo=algo,
        train_data_nodes=train_data_nodes,
        test_data_nodes=test_data_nodes,
    )

    # Computation graph is created
    # TODO: static checks on the graph

    authorized_ids = list(set([aggregation_node.node_id] + [node.node_id for node in train_data_nodes]))
    permissions = substra.sdk.schemas.Permissions(public=False, authorized_ids=authorized_ids)

    # Register all operations in substra
    # Define the algorithms we need and submit them
    logger.info("Submitting the algorithm to Connect.")
    composite_traintuples = []
    for train_node in train_data_nodes:
        train_node.register_operations(client, permissions, dependencies=dependencies)
        composite_traintuples += train_node.tuples

    testtuples = []
    for test_node in test_data_nodes:
        test_node.register_operations(client, permissions, dependencies=dependencies)
        testtuples += test_node.tuples

    # The aggregation operation is defined in the strategy, its dependencies are
    # the strategy dependencies
    aggregation_node.register_operations(client, permissions, dependencies=None)

    # Execute the compute plan
    logger.info("Submitting the compute plan to Connect.")
    compute_plan = client.add_compute_plan(
        substra.sdk.schemas.ComputePlanSpec(
            composite_traintuples=composite_traintuples,
            aggregatetuples=aggregation_node.tuples,
            testtuples=testtuples,
            tag=str(datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")),
            clean_models=True,  # set it to False if users need the intermediary models
        ),
        auto_batching=False,
    )

    logger.info(("The compute plan has been submitted to Connect, its key is {0}.").format(compute_plan.key))

    return compute_plan
