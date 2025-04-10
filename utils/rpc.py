import asyncio
import eth_abi
import tenacity
import asyncio

from functools import wraps
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
from aiolimiter import AsyncLimiter
from eth_abi.codec import ABICodec
from eth_utils.crypto import keccak
from hexbytes import HexBytes
from httpx import AsyncClient
from httpx import AsyncHTTPTransport
from httpx import Limits
from httpx import Timeout
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_random_exponential
from web3 import AsyncHTTPProvider
from web3 import AsyncWeb3
from web3 import Web3
from web3._utils.events import get_event_data
from web3.contract import AsyncContract

from utils.exceptions import RPCException
from utils.logging import logger
from utils.models.settings_model import RPCConfigFull
from config.loader import get_core_config

settings = get_core_config()

# Create a module-specific logger
logger = logger.bind(module='RpcHelper')


def get_contract_abi_dict(abi):
    """
    Returns a dictionary of function signatures, inputs, outputs and full ABI for a given contract ABI.

    Args:
        abi (list): List of dictionaries representing the contract ABI.

    Returns:
        dict: Dictionary containing function signatures, inputs, outputs and full ABI.
    """
    abi_dict = {}
    for abi_obj in [obj for obj in abi if obj['type'] == 'function']:
        name = abi_obj['name']
        input_types = [input['type'] for input in abi_obj['inputs']]
        output_types = [output['type'] for output in abi_obj['outputs']]
        abi_dict[name] = {
            'signature': '{}({})'.format(name, ','.join(input_types)),
            'output': output_types,
            'input': input_types,
            'abi': abi_obj,
        }

    return abi_dict


def get_encoded_function_signature(abi_dict, function_name, params: Union[List, None]):
    """
    Returns the encoded function signature for a given function name and parameters.

    Args:
        abi_dict (dict): The ABI dictionary for the contract.
        function_name (str): The name of the function.
        params (list or None): The list of parameters for the function.

    Returns:
        str: The encoded function signature.
    """
    function_signature = abi_dict.get(function_name)['signature']
    encoded_signature = '0x' + keccak(text=function_signature).hex()[:8]
    if params:
        encoded_signature += eth_abi.encode(
            abi_dict.get(function_name)['input'],
            params,
        ).hex()
    return encoded_signature


def get_event_sig_and_abi(event_signatures, event_abis):
    """
    Given a dictionary of event signatures and a dictionary of event ABIs,
    returns a tuple containing a list of event signatures and a dictionary of
    event ABIs keyed by their corresponding signature hash.

    Args:
        event_signatures (dict): Dictionary of event signatures.
        event_abis (dict): Dictionary of event ABIs.

    Returns:
        tuple: A tuple containing:
            - list: List of event signatures.
            - dict: Dictionary of event ABIs keyed by their signature hash.
    """
    event_sig = [
        '0x' + keccak(text=sig).hex() for name, sig in event_signatures.items()
    ]
    event_abi = {
        '0x' +
        keccak(text=sig).hex(): event_abis.get(
            name,
            'incorrect event name',
        )
        for name, sig in event_signatures.items()
    }
    return event_sig, event_abi


def acquire_rpc_semaphore(fn):
    """
    A decorator function that acquires a bounded semaphore before executing the decorated function and releases it
    after the function is executed. This decorator is intended to be used with async functions.

    Args:
        fn: The async function to be decorated.

    Returns:
        The decorated async function.
    """
    @wraps(fn)
    async def wrapped(self, *args, **kwargs):
        sem: asyncio.BoundedSemaphore = self._semaphore
        await sem.acquire()
        result = None
        try:
            result = await fn(self, *args, **kwargs)
            return result
        except Exception as e:
            logger.opt(exception=settings.logs.debug_mode).error(
                'Error in asyncio semaphore acquisition decorator: {}', e,
            )
            raise e
        finally:
            sem.release()
    return wrapped


class RpcHelper(object):
    def __init__(self, rpc_settings: RPCConfigFull, archive_mode=False, source_node: bool = False):
        """
        Initializes an instance of the RpcHelper class.

        Args:
            rpc_settings (RPCConfigBase, optional): The RPC configuration settings to use. Defaults to settings.rpc.
            archive_mode (bool, optional): Whether to operate in archive mode. Defaults to False.
        """
        self._archive_mode = archive_mode
        self._rpc_settings = rpc_settings
        self._nodes = list()
        self._current_node_index = 0
        self._node_count = 0
        self._initialized = False
        self._sync_nodes_initialized = False
        self._logger = logger
        self._client = None
        self._async_transport = None
        self._semaphore = None
        self._source_node = source_node

    async def _init_http_clients(self):
        """
        Initializes the HTTP clients for making RPC requests.

        If the client has already been initialized, this function returns immediately.

        :return: None
        """
        if self._client is not None:
            return
        self._async_transport = AsyncHTTPTransport(
            limits=Limits(
                max_connections=self._rpc_settings.connection_limits.max_connections,
                max_keepalive_connections=self._rpc_settings.connection_limits.max_keepalive_connections,
                keepalive_expiry=self._rpc_settings.connection_limits.keepalive_expiry,
            ),
        )
        self._client = AsyncClient(
            timeout=Timeout(timeout=15.0),
            follow_redirects=False,
            transport=self._async_transport,
        )

    async def _load_async_web3_providers(self):
        """
        Loads async web3 providers for each node in the list of nodes.
        If a node already has a web3 client, it is skipped.
        """
        for node in self._nodes:
            node['web3_client_async'] = AsyncWeb3(
                AsyncHTTPProvider(node['rpc_url']),
            )
            self._logger.debug('Loaded async web3 provider for node {}: {}', node['rpc_url'], node['web3_client_async'])
        self._logger.debug('Post async web3 provider loading: {}', self._nodes)

    async def init(self):
        """
        Initializes the RPC client by loading web3 providers and rate limits,
        loading rate limit SHAs, initializing HTTP clients, and loading async
        web3 providers.

        Returns:
            None
        """
        if not self._initialized:
            self._semaphore = asyncio.BoundedSemaphore(value=settings.source_rpc.semaphore_value)

            if not self._sync_nodes_initialized:
                self._logger.debug('Sync nodes not initialized, initializing...')
                self.sync_init()
            if self._nodes:
                await self._init_http_clients()
                # load async web3 providers
                for node in self._nodes:
                    node['web3_client_async'] = AsyncWeb3(
                        AsyncHTTPProvider(node['rpc_url']),
                    )
                    self._logger.debug(
                        'Loaded async web3 provider for node {}: {}',
                        node['rpc_url'], node['web3_client_async'],
                    )
                self._logger.debug('Post async web3 provider loading: {}', self._nodes)
                self._initialized = True
                self._logger.debug('RPC client initialized')
            else:
                self._logger.error('No full nor archive nodes found in config')

    def sync_init(self):
        """
        Initializes the synchronous nodes for the RPC client.

        This method sets up the Web3 providers for each node specified in the configuration.
        It handles both full nodes and archive nodes based on the archive_mode setting.

        Raises:
            Exception: If no full or archive nodes are found in the configuration.
        """
        if self._sync_nodes_initialized:
            return
        if self._archive_mode:
            nodes = self._rpc_settings.archive_nodes
        else:
            nodes = self._rpc_settings.full_nodes
        if not nodes:
            self._logger.error('No full nor archive nodes found in config')
            raise Exception('No full nor archive nodes found in config')
        for node in nodes:
            self._nodes.append(
                {
                    'web3_client': Web3(Web3.HTTPProvider(node.url)),
                    'web3_client_async': None,
                    'rpc_url': node.url,
                    'rate_limiter': AsyncLimiter(
                        max(1, node.rate_limit.requests_per_second),
                        1,
                    ),
                },
            )
            self._logger.debug('Loaded RPC settings for node {}', node.url)
        self._node_count = len(self._nodes)
        self._sync_nodes_initialized = True

    def get_current_node(self):
        """
        Returns the current node to use for RPC calls.

        If there are no full nodes available, it raises an exception.

        Returns:
            dict: The current node to use for RPC calls.

        Raises:
            Exception: If no full nodes are available.
        """
        if self._node_count == 0:
            raise Exception('No full nodes available')
        return self._nodes[self._current_node_index]

    @acquire_rpc_semaphore
    async def get_transaction_from_hash(self, tx_hash: str):
        """
        Retrieves the transaction details from the blockchain.

        Args:
            tx_hash (str): The hash of the transaction to retrieve.

        Returns:
            dict: The transaction details.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            node = self._nodes[node_idx]
            web3_provider = node['web3_client_async']

            try:
                transaction = await web3_provider.eth.get_transaction(tx_hash)
                return transaction
            except Exception as e:
                exc = RPCException(
                    request={'txHash': tx_hash},
                    response=None,
                    underlying_exception=e,
                    extra_info=f'RPC_GET_TRANSACTION_ERROR: {str(e)}',
                )
                self._logger.trace('Error in get_transaction_from_hash, error {}', str(exc))
                raise exc

        return await f(node_idx=0)

    def _on_node_exception(self, retry_state: tenacity.RetryCallState):
        """
        Callback function to handle exceptions raised during RPC calls to nodes.
        It updates the node index to retry the RPC call on the next node.

        Args:
            retry_state (tenacity.RetryCallState): The retry state object containing information about the retry.

        Returns:
            None
        """
        exc_idx = retry_state.kwargs['node_idx']
        next_node_idx = (retry_state.kwargs.get('node_idx', 0) + 1) % self._node_count
        retry_state.kwargs['node_idx'] = next_node_idx
        self._logger.warning(
            'Found exception while performing RPC {} on node {} at idx {}. '
            'Injecting next node {} at idx {} | exception: {} ',
            retry_state.fn, self._nodes[exc_idx], exc_idx, self._nodes[next_node_idx],
            next_node_idx, retry_state.outcome.exception(),
        )

    async def _rate_limited_call(self, coroutine, node_idx):
        async with self._nodes[node_idx]['rate_limiter']:
            return await coroutine

    @acquire_rpc_semaphore
    async def get_current_block_number(self):
        """
        Returns:
            int: The current block number of the Ethereum blockchain.

        Raises:
            RPCException: If an error occurs while making the RPC call.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            node = self._nodes[node_idx]
            web3_provider = node['web3_client_async']

            try:
                current_block = await self._rate_limited_call(web3_provider.eth.block_number, node_idx)
            except Exception as e:
                exc = RPCException(
                    request='get_current_block_number',
                    response=None,
                    underlying_exception=e,
                    extra_info=f'RPC_GET_CURRENT_BLOCKNUMBER ERROR: {str(e)}',
                )
                self._logger.trace('Error in get_current_block_number, error {}', str(exc))
                raise exc
            else:
                return current_block
        return await f(node_idx=0)

    @acquire_rpc_semaphore
    async def get_transaction_receipt(self, tx_hash):
        """
        Retrieves the transaction receipt for a given transaction hash.

        Args:
            tx_hash (str): The transaction hash for which to retrieve the receipt.

        Returns:
            dict: The transaction receipt details as a dictionary.

        Raises:
            RPCException: If an error occurs while retrieving the transaction receipt.
        """

        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            node = self._nodes[node_idx]

            try:
                tx_receipt_details = await self._rate_limited_call(
                    node['web3_client_async'].eth.get_transaction_receipt(tx_hash),
                    node_idx,
                )
            except Exception as e:
                exc = RPCException(
                    request={
                        'txHash': tx_hash,
                    },
                    response=None,
                    underlying_exception=e,
                    extra_info=f'RPC_GET_TRANSACTION_RECEIPT_ERROR: {str(e)}',
                )
                self._logger.trace('Error in get transaction receipt for tx hash {}, error {}', tx_hash, str(exc))
                raise exc
            else:
                return tx_receipt_details
        return await f(node_idx=0)

    @acquire_rpc_semaphore
    async def get_current_block(self, node_idx=0):
        """
        Returns the current block number of the Ethereum blockchain.

        Args:
            node_idx (int): Index of the node to use for the RPC call.

        Returns:
            int: The current block number of the Ethereum blockchain.

        Raises:
            RPCException: If an error occurs while making the RPC call.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            node = self._nodes[node_idx]
            web3_provider = node['web3_client_async']

            try:
                current_block = await self._rate_limited_call(web3_provider.eth.block_number, node_idx)
            except Exception as e:
                exc = RPCException(
                    request='get_current_block_number',
                    response=None,
                    underlying_exception=e,
                    extra_info=f'RPC_GET_CURRENT_BLOCKNUMBER ERROR: {str(e)}',
                )
                self._logger.trace('Error in get_current_block_number, error {}', str(exc))
                raise exc
            else:
                return current_block
        return await f(node_idx=0)

    @acquire_rpc_semaphore
    async def web3_call(self, tasks, contract_addr, abi):
        """
        Calls the given tasks asynchronously using web3 and returns the response.

        Args:
            tasks (list): List of tuples of (contract functions, contract args) to call. By name.
            contract_addr (str): Address of the contract to call.
            abi (dict): ABI of the contract.

        Returns:
            list: List of responses from the contract function calls.

        Raises:
            RPCException: If an error occurs during the web3 batch call.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            try:
                node = self._nodes[node_idx]
                contract_obj = node['web3_client_async'].eth.contract(
                    address=contract_addr,
                    abi=abi,
                )
                web3_tasks = [
                    self._rate_limited_call(
                        contract_obj.functions[task[0]](*task[1]).call(),
                        node_idx,
                    ) for task in tasks
                ]
                response = await asyncio.gather(*web3_tasks)
                return response
            except Exception as e:
                # Create a serializable version of the tasks
                serializable_tasks = [
                    {
                        'function_name': task[0],
                        'args': task[1],
                    } for task in tasks
                ]
                exc = RPCException(
                    request=serializable_tasks,
                    response=None,
                    underlying_exception=e,
                    extra_info={'msg': str(e)},
                )
                self._logger.opt(exception=settings.logs.debug_mode).error(
                    (
                        'Error while making web3 batch call'
                    ),
                    err=str(exc),
                )
                raise exc
        return await f(node_idx=0)

    @acquire_rpc_semaphore
    async def web3_call_with_override(self, tasks, contract_addr, abi, overrides):
        """
        Calls the given tasks asynchronously using web3 and returns the response.
        Supports overriding of the contract state.

        Args:
            tasks (list): List of tuples of (contract functions, contract args) to call. By name.
            contract_addr (str): Address of the contract to call.
            abi (dict): ABI of the contract.
            overrides (dict): State overrides for the call.

        Returns:
            list: List of responses from the contract function calls.

        Raises:
            RPCException: If an error occurs during the web3 batch call.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            try:
                node = self._nodes[node_idx]
                contract_obj = node['web3_client_async'].eth.contract(
                    address=contract_addr,
                    abi=abi,
                )
                web3_tasks = []
                for task in tasks:
                    function_name, args = task
                    function = contract_obj.functions[function_name]
                    call_data = function(*args)._encode_transaction_data()
                    payload = {
                        'to': contract_addr,
                        'data': call_data,
                    }
                    web3_tasks.append(
                        self._rate_limited_call(
                            node['web3_client_async'].eth.call(payload, state_override=overrides),
                            node_idx,
                        ),
                    )

                raw_results = await asyncio.gather(*web3_tasks)

                # Decode the results using eth_abi
                decoded_results = []
                for i, result in enumerate(raw_results):
                    function_name, _ = tasks[i]
                    function_abi = next(func for func in abi if func['name'] == function_name)
                    output_types = [output['type'] for output in function_abi['outputs']]
                    decoded_result = eth_abi.decode(output_types, result)
                    # If there's only one output, return it directly; otherwise, return the tuple
                    decoded_results.append(decoded_result[0] if len(decoded_result) == 1 else decoded_result)

                return decoded_results
            except Exception as e:
                # Create a serializable version of the tasks
                serializable_tasks = [
                    {
                        'function_name': task[0],
                        'args': task[1],
                    } for task in tasks
                ]
                exc = RPCException(
                    request=serializable_tasks,
                    response=None,
                    underlying_exception=e,
                    extra_info={'msg': str(e)},
                )
                self._logger.opt(exception=settings.logs.debug_mode).error(
                    (
                        'Error while making web3 batch call'
                    ),
                    err=str(exc),
                )
                raise exc
        return await f(node_idx=0)

    @acquire_rpc_semaphore
    async def batch_web3_contract_calls(
        self,
        tasks: List[Tuple[str, List[Any]]],
        contract_obj: AsyncContract,
        block_override: Optional[List[int]] = None,
    ) -> List[Any]:
        """
        Performs batch web3 calls for multiple contract functions.

        Args:
            contract_obj: Web3 contract object.
            tasks: List of tuples, each containing (function_name, function_args).
            block_override: Optional list of block numbers to override 'latest' for each call.

        Returns:
            List[Any]: List of results from the batch call.
        """

        if block_override and len(block_override) != len(tasks):
            self._logger.error(
                'Block override length {} is not equal to the number of tasks {}.',
                len(block_override), len(tasks),
            )
            raise ValueError('Block override length is not equal to the number of tasks')

        # Prepare batch request
        batch = []
        req_id = 1
        for i, task in enumerate(tasks):
            block = hex(block_override[i]) if block_override else 'latest'
            function = contract_obj.functions[task[0]]
            call_data = function(*task[1])._encode_transaction_data()
            batch.append({
                'jsonrpc': '2.0',
                'method': 'eth_call',
                'params': [
                    {
                        'to': contract_obj.address,
                        'data': call_data,
                    }, block,
                ],
                'id': req_id,
            })
            req_id += 1

        try:
            # Make batch RPC call
            response_data = await self._make_rpc_jsonrpc_call(batch)
            # Process responses
            results = []
            abi_dict = get_contract_abi_dict(contract_obj.abi)
            for i, response in enumerate(response_data):
                if 'result' in response:
                    function_name, _ = tasks[i]
                    decoded_result = eth_abi.decode(
                        abi_dict.get(function_name)['output'],
                        HexBytes(response['result']),
                    )
                    results.append(decoded_result[0] if len(decoded_result) == 1 else decoded_result)
                else:
                    # Handle individual response errors
                    raise RPCException(
                        request=batch[i],
                        response=response,
                        underlying_exception=None,
                        extra_info=f'Error in batch call for function {tasks[i][0]}',
                    )

            return results
        except Exception as e:
            exc = RPCException(
                request=batch,
                response=None,
                underlying_exception=e,
                extra_info=f'RPC_BATCH_CALL_ERROR: {str(e)}',
            )
            self._logger.trace('Error in batch_web3_calls, error {}', str(exc))
            raise exc

    @acquire_rpc_semaphore
    async def _make_rpc_jsonrpc_call(self, rpc_query, redis_conn=None):
        """
        Makes an RPC JSON-RPC call to a node in the pool.

        Args:
            rpc_query (dict): The JSON-RPC query to be sent.

        Returns:
            dict: The JSON-RPC response data.

        Raises:
            RPCException: If there is an error in making the JSON-RPC call.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):

            node = self._nodes[node_idx]
            rpc_url = node.get('rpc_url')
            try:
                response = await self._rate_limited_call(
                    self._client.post(url=rpc_url, json=rpc_query),
                    node_idx,
                )
                response_data = response.json()
            except Exception as e:
                exc = RPCException(
                    request=rpc_query,
                    response=None,
                    underlying_exception=e,
                    extra_info=f'RPC call error | REQUEST: {rpc_query} | Exception: {str(e)}',
                )
                self._logger.trace(
                    'Error in making jsonrpc call, error {}', str(exc),
                )
                raise exc

            if response.status_code != 200:
                raise RPCException(
                    request=rpc_query,
                    response=(response.status_code, response.text),
                    underlying_exception=None,
                    extra_info=f'RPC_CALL_ERROR: {response.text}',
                )

            response_exceptions = []
            return_response_data = None
            trie_node_exc = False
            if isinstance(response_data, list):
                return_response_list = []
                for response_item in response_data:
                    if 'error' in response_item:
                        if isinstance(response_item['error'], dict) and 'message' in response_item['error'] and 'missing trie node' in response_item['error']['message']:
                            # do not raise exception for missing trie node error, further retries will only be wasteful
                            trie_node_exc = True
                            continue
                        response_exceptions.append(response_item['error'])
                    else:
                        return_response_list.append(response_item)
                return_response_data = return_response_list
            else:
                if 'error' in response_data:
                    if isinstance(response_data['error'], dict) and 'message' in response_data['error'] and 'missing trie node' in response_data['error']['message']:
                        # do not raise exception for missing trie node error, further retries will only be wasteful
                        trie_node_exc = True
                    response_exceptions.append(response_data['error'])
                else:   # if response is not a list, it is a dict
                    return_response_data = response_data

            if response_exceptions and not trie_node_exc:
                raise RPCException(
                    request=rpc_query,
                    response=response_data,
                    underlying_exception=response_exceptions,
                    extra_info=f'RPC_BATCH_ETH_CALL_ERROR: {response_exceptions}',
                )

            return return_response_data
        return await f(node_idx=0)

    async def batch_eth_get_balance_on_block_range(
            self,
            address,
            from_block,
            to_block,
    ):
        """
        Batch retrieves the Ethereum balance of an address for a range of blocks.

        Args:
            address (str): The Ethereum address to retrieve the balance for.
            from_block (int): The starting block number.
            to_block (int): The ending block number.

        Returns:
            list: A list of Ethereum balances for each block in the range. If a balance could not be retrieved for a block,
            None is returned in its place.
        """
        rpc_query = []
        request_id = 1
        for block in range(from_block, to_block + 1):
            rpc_query.append(
                {
                    'jsonrpc': '2.0',
                    'method': 'eth_getBalance',
                    'params': [address, hex(block)],
                    'id': request_id,
                },
            )
            request_id += 1

        try:
            response_data = await self._make_rpc_jsonrpc_call(rpc_query)

            rpc_response = []
            if isinstance(response_data, list):
                response = response_data
            elif response_data is not None and isinstance(response_data, dict):
                response = [response_data]
            for result in response:
                if 'result' in result:
                    eth_balance = result['result']
                    eth_balance = int(eth_balance, 16)
                    rpc_response.append(eth_balance)
            return rpc_response
        except Exception as e:
            exc = RPCException(
                request=rpc_query,
                response=None,
                underlying_exception=e,
                extra_info=f'RPC_BATCH_ETH_GET_BALANCE_ON_BLOCK_RANGE_ERROR: {str(e)}',
            )
            self._logger.trace('Error in batch_eth_get_balance_on_block_range, error {}', str(exc))
            raise exc

    async def batch_eth_call_on_block_range(
        self,
        abi_dict,
        function_name,
        contract_address,
        from_block,
        to_block,
        params: Union[List, None] = None,
        from_address=Web3.to_checksum_address('0x0000000000000000000000000000000000000000'),
    ):
        """
        Batch executes an Ethereum contract function call on a range of blocks.

        Args:
            abi_dict (dict): The ABI dictionary of the contract.
            function_name (str): The name of the function to call.
            contract_address (str): The address of the contract.
            from_block (int): The starting block number.
            to_block (int): The ending block number.
            params (list, optional): The list of parameters to pass to the function. Defaults to None.
            from_address (str, optional): The address to use as the sender of the transaction. Defaults to '0x0000000000000000000000000000000000000000'.

        Returns:
            list: A list of decoded results from the function call.
        """
        if params is None:
            params = []

        function_signature = get_encoded_function_signature(
            abi_dict, function_name, params,
        )
        rpc_query = []
        request_id = 1
        for block in range(from_block, to_block + 1):
            rpc_query.append(
                {
                    'jsonrpc': '2.0',
                    'method': 'eth_call',
                    'params': [
                        {
                            'from': from_address,
                            'to': Web3.to_checksum_address(contract_address),
                            'data': function_signature,
                        },
                        hex(block),
                    ],
                    'id': request_id,
                },
            )
            request_id += 1

        response_data = await self._make_rpc_jsonrpc_call(rpc_query)
        rpc_response = []
        if isinstance(response_data, list):
            response = response_data
        else:
            if response_data is not None and isinstance(response_data, dict):
                response = [response_data]
        for result in response:
            if 'result' in result:
                rpc_response.append(
                    eth_abi.decode(
                        abi_dict.get(
                            function_name,
                        )['output'],
                        HexBytes(result['result']),
                    ),
                )
        return rpc_response

    async def batch_eth_call_on_block_range_hex_data(
        self,
        abi_dict,
        function_name,
        contract_address,
        from_block,
        to_block,
        params: Union[List, None] = None,
        from_address=Web3.to_checksum_address('0x0000000000000000000000000000000000000000'),
    ):
        """
        Batch executes an Ethereum contract function call on a range of blocks and returns raw HexBytes data.

        Args:
            abi_dict (dict): The ABI dictionary of the contract.
            function_name (str): The name of the function to call.
            contract_address (str): The address of the contract.
            from_block (int): The starting block number.
            to_block (int): The ending block number.
            params (list, optional): The list of parameters to pass to the function. Defaults to None.
            from_address (str, optional): The address to use as the sender of the transaction. Defaults to '0x0000000000000000000000000000000000000000'.

        Returns:
            list: A list of raw HexBytes data results from the function call.
        """
        if params is None:
            params = []

        function_signature = get_encoded_function_signature(
            abi_dict, function_name, params,
        )
        rpc_query = []
        request_id = 1
        for block in range(from_block, to_block + 1):
            rpc_query.append(
                {
                    'jsonrpc': '2.0',
                    'method': 'eth_call',
                    'params': [
                        {
                            'from': from_address,
                            'to': Web3.to_checksum_address(contract_address),
                            'data': function_signature,
                        },
                        hex(block),
                    ],
                    'id': request_id,
                },
            )
            request_id += 1

        response_data = await self._make_rpc_jsonrpc_call(rpc_query)
        rpc_response = []

        # Return the hexbytes data to be decoded outside the function
        if isinstance(response_data, list):
            response = response_data
        else:
            if response_data is not None and isinstance(response_data, dict):
                response = [response_data]
        for result in response:
            rpc_response.append(HexBytes(result['result']))

        return rpc_response

    async def batch_eth_get_block(self, from_block, to_block):
        """
        Batch retrieves Ethereum blocks using eth_getBlockByNumber JSON-RPC method.

        Args:
            from_block (int): The block number to start retrieving from.
            to_block (int): The block number to stop retrieving at.

        Returns:
            dict: A dictionary containing the response data from the JSON-RPC call.
        """
        rpc_query = []

        request_id = 1
        for block in range(from_block, to_block + 1):
            rpc_query.append(
                {
                    'jsonrpc': '2.0',
                    'method': 'eth_getBlockByNumber',
                    'params': [
                        hex(block),
                        False,
                    ],
                    'id': request_id,
                },
            )
            request_id += 1

        response_data = await self._make_rpc_jsonrpc_call(rpc_query)
        return response_data

    @acquire_rpc_semaphore
    async def get_events_logs(
        self, contract_address, to_block, from_block, topics, event_abi,
    ):
        """
        Returns all events logs for a given contract address, within a specified block range and with specified topics.

        Args:
            contract_address (str): The address of the contract to get events logs for.
            to_block (int): The highest block number to retrieve events logs from.
            from_block (int): The lowest block number to retrieve events logs from.
            topics (List[str]): A list of topics to filter the events logs by.
            event_abi (Dict): The ABI of the event to decode the logs with.

        Returns:
            List[Dict]: A list of dictionaries representing the decoded events logs.

        Raises:
            RPCException: If there's an error in retrieving or processing the event logs.
        """
        @retry(
            reraise=True,
            retry=retry_if_exception_type(RPCException),
            wait=wait_random_exponential(multiplier=1, max=10),
            stop=stop_after_attempt(settings.source_rpc.retry),
            before_sleep=self._on_node_exception,
        )
        async def f(node_idx):
            node = self._nodes[node_idx]
            rpc_url = node.get('rpc_url')

            web3_provider = node['web3_client_async']

            event_log_query = {
                'address': Web3.to_checksum_address(contract_address),
                'toBlock': to_block,
                'fromBlock': from_block,
                'topics': topics,
            }
            try:
                event_log = await self._rate_limited_call(
                    web3_provider.eth.get_logs(event_log_query),
                    node_idx,
                )
                codec: ABICodec = web3_provider.codec
                all_events = []
                for log in event_log:
                    abi = event_abi.get(log.topics[0].hex(), '')
                    evt = get_event_data(codec, abi, log)
                    all_events.append(evt)

                return all_events
            except Exception as e:
                exc = RPCException(
                    request={
                        'contract_address': contract_address,
                        'to_block': to_block,
                        'from_block': from_block,
                        'topics': topics,
                    },
                    response=None,
                    underlying_exception=e,
                    extra_info=f'RPC_GET_EVENT_LOGS_ERROR: {str(e)}',
                )
                self._logger.trace('Error in get_events_logs, error {}', str(exc))
                raise exc

        return await f(node_idx=0)

    async def eth_get_block(self, block_number=None):
        """
        Batch retrieves Ethereum blocks using eth_getBlockByNumber JSON-RPC method.
        Args:
            block_number (int): The block number to retrieve.
        Returns:
            JSON-RPC response: A response containing the block data from the JSON-RPC call to fetch the respective block.
        """
        if not self._initialized:
            await self.init()

        rpc_query = []
        block = hex(block_number) if block_number is not None else 'latest'
        request_id = 1
        rpc_query.append(
            {
                'jsonrpc': '2.0',
                'method': 'eth_getBlockByNumber',
                'params': [
                    block,
                    False,
                ],
                'id': request_id,
            },
        )

        response_data = await self._make_rpc_jsonrpc_call(rpc_query)
        return response_data[0]['result']
