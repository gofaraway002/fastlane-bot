# coding=utf-8
"""
Contains the manager module for handling contract functionality within the events updater.

(c) Copyright Bprotocol foundation 2023.
Licensed under MIT
"""
from typing import Dict, Any, Tuple

import pandas as pd
from web3 import Web3
from web3.contract import Contract

from fastlane_bot.data.abi import BANCOR_V3_NETWORK_INFO_ABI, ERC20_ABI, BANCOR_POL_ABI
from fastlane_bot.events.managers.base import BaseManager


class ContractsManager(BaseManager):
    def init_tenderly_event_contracts(self):
        """
        Initialize the tenderly event contracts.
        """

        for exchange_name in self.tenderly_event_exchanges:
            address = None
            if exchange_name != "bancor_pol":
                raise NotImplementedError(
                    f"Exchange {exchange_name} not supported for tenderly"
                )
            if address := self.cfg.BANCOR_POL_ADDRESS:
                self.tenderly_event_contracts[
                    exchange_name
                ] = self.w3_tenderly.eth.contract(
                    address=address,
                    abi=self.exchanges[exchange_name].get_abi(),
                )

    def init_exchange_contracts(self):
        """
        Initialize the exchange contracts.
        """
        for exchange_name in self.SUPPORTED_EXCHANGES:
            self.event_contracts[exchange_name] = self.web3.eth.contract(
                abi=self.exchanges[exchange_name].get_abi(),
            )
            self.pool_contracts[exchange_name] = {}
            if exchange_name == "bancor_v3":
                self.pool_contracts[exchange_name][
                    self.cfg.BANCOR_V3_NETWORK_INFO_ADDRESS
                ] = self.web3.eth.contract(
                    address=self.cfg.BANCOR_V3_NETWORK_INFO_ADDRESS,
                    abi=BANCOR_V3_NETWORK_INFO_ABI,
                )
            elif exchange_name == "bancor_pol":
                self.pool_contracts[exchange_name][
                    self.cfg.BANCOR_POL_ADDRESS
                ] = self.web3.eth.contract(
                    address=self.cfg.BANCOR_POL_ADDRESS,
                    abi=BANCOR_POL_ABI,
                )
            elif exchange_name == 'carbon_v1':
                self.pool_contracts[exchange_name][
                    self.cfg.CARBON_CONTROLLER_ADDRESS
                ] = self.web3.eth.contract(
                    address=self.cfg.CARBON_CONTROLLER_ADDRESS,
                    abi=self.exchanges[exchange_name].get_abi(),
                )

    @staticmethod
    def get_or_create_token_contracts(
            web3: Web3,
            erc20_contracts: Dict[str, Contract],
            address: str,
            exchange_name: str = None,
            tenderly_fork_id: str = None,
    ) -> Contract:
        """
        Get or create the token contracts.

        Parameters
        ----------
        web3 : Web3
            The Web3 instance.
        erc20_contracts : Dict[str, Contract]
            The ERC20 contracts.
        address : str
            The address.
        exchange_name : str, optional
            The exchange name.
        tenderly_fork_id : str, optional
            The tenderly fork id.

        Returns
        -------
        Contract
            The token contract.

        """
        if exchange_name == "bancor_pol" and tenderly_fork_id:
            w3 = Web3(
                Web3.HTTPProvider(f"https://rpc.tenderly.co/fork/{tenderly_fork_id}")
            )
            contract = w3.eth.contract(abi=ERC20_ABI, address=address)
        elif address in erc20_contracts:
            contract = erc20_contracts[address]
        else:
            contract = web3.eth.contract(address=address, abi=ERC20_ABI)
            erc20_contracts[address] = contract
        return contract

    def add_pool_info_from_contract(
            self,
            exchange_name: str = None,
            address: str = None,
            event: Any = None,
    ) -> Dict[str, Any]:
        """
        Add the pool info from the contract.

        Parameters
        ----------
        exchange_name : str, optional
            The exchange name.
        address : str, optional
            The address.
        event : Any, optional
            The event.

        Returns
        -------
        Dict[str, Any]
            The pool info from the contract.

        """
        exchange_name = self.check_forked_exchange_names(exchange_name, address, event)
        if not exchange_name:
            self.cfg.logger.info(f"Exchange name not found {event}")
            return None

        if exchange_name not in self.SUPPORTED_EXCHANGES:
            self.cfg.logger.debug(
                f"Event exchange {exchange_name} not in exchanges={self.SUPPORTED_EXCHANGES} for address={address}"
            )
            return None

        pool_contract = self.get_pool_contract(exchange_name, address)
        self.pool_contracts[exchange_name][address] = pool_contract
        fee, fee_float = self.exchanges[exchange_name].get_fee(address, pool_contract)

        t0_addr = self.exchanges[exchange_name].get_tkn0(address, pool_contract, event)
        t1_addr = self.exchanges[exchange_name].get_tkn1(address, pool_contract, event)
        block_number = event["blockNumber"]

        return self.add_pool_info(
            address=address,
            exchange_name=exchange_name,
            fee=fee,
            fee_float=fee_float,
            tkn0_address=t0_addr,
            tkn1_address=t1_addr,
            cid=event["args"]["id"] if exchange_name == "carbon_v1" else None,
            contract=pool_contract,
            block_number=block_number,
        )

    def get_pool_contract(self, exchange_name: str, address: str) -> Contract:
        """
        Get the pool contract.

        Parameters
        ----------
        exchange_name : str
            The exchange name.
        address : str
            The address.

        Returns
        -------
        Contract
            The pool contract.

        """
        if exchange_name not in self.exchanges:
            return None

        w3 = self.web3

        contract_key = (
            self.cfg.BANCOR_V3_NETWORK_INFO_ADDRESS
            if exchange_name == "bancor_v3"
            else self.cfg.BANCOR_POL_ADDRESS
            if exchange_name == "bancor_pol"
            else address
        )
        return self.pool_contracts[exchange_name].get(
            contract_key,
            w3.eth.contract(
                address=contract_key, abi=self.exchanges[exchange_name].get_abi()
            ),
        )

    @staticmethod
    def get_tkn_key(symbol: str, addr: str) -> str:
        if symbol is None or symbol == "None" or addr is None:
            print(addr)
        return f"{symbol}-{addr[-4:]}"

    def get_token_info_from_contract(
            self, web3: Web3, erc20_contracts: Dict[str, Contract], addr: str
    ) -> Tuple[str, int]:
        """
        Get the token info from contract.

        Parameters
        ----------
        web3 : Web3
            The web3 instance.
        erc20_contracts : Dict[str, Contract]
            The erc20 contracts.
        addr : str
            The address.

        Returns
        -------
        Tuple[str, int]
            The token info.

        """
        contract = self.get_or_create_token_contracts(web3, erc20_contracts, addr)
        tokens_filepath = 'fastlane_bot/data/tokens.csv'
        token_data = pd.read_csv(tokens_filepath)

        try:
            return self._get_and_save_token_info_from_contract(
                contract=contract, addr=addr, token_data=token_data, tokens_filepath=tokens_filepath
            )
        except Exception as e:
            self.cfg.logger.debug(f"Failed to get symbol and decimals for {addr} {e}")

    def _get_and_save_token_info_from_contract(self, contract: Contract, addr: str, token_data: pd.DataFrame,
                                               tokens_filepath: str) -> Tuple[str, int]:
        """
        Get and save the token info from contract to csv.

        Parameters
        ----------
        contract : Contract
            The contract.
        addr : str
            The address.
        token_data : pd.DataFrame
            The token data.
        tokens_filepath : str
            The tokens filepath.

        Returns
        -------
        Tuple[str, int]
            The token info.

        """
        symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
        key = self.get_tkn_key(symbol=symbol, addr=addr)
        new_data = {
            "key": key,
            "symbol": symbol,
            "name": symbol,
            "address": addr,
            "decimals": decimals
        }
        row = pd.DataFrame(new_data, index=max(token_data.index) + 1, columns=token_data.columns)
        token_data = pd.concat([token_data, row])
        token_data.to_csv(tokens_filepath)

        return (
            symbol, decimals
        )
