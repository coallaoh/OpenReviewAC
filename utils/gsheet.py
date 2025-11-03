import logging
from gsheet_manager import GSheetManager
import tqdm


class GSheetWithHeader(GSheetManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._headers = None

    @property
    def headers(self):
        if self._headers is None and self.local_sheet_values:
            self._headers = self.local_sheet_values[0]
        return self._headers

    def clear_worksheet(self):
        self._worksheet.clear()
        self._headers = None
        logging.info("Worksheet cleared")

    def get_data_list(self):
        self.sync_from_remote()
        data_list = []
        for row in self.local_sheet_values[1:]:
            data_list.append(dict(zip(self.headers, row)))
        logging.info(f"Retrieved {len(data_list)} rows of data")
        return data_list

    @GSheetManager.batch_sync_with_remote
    def _write_headers(self, headers, start_row_idx=0, overwrite=False):
        current_row_idx = start_row_idx
        current_header_idx = len(self.headers) if self.headers else 0
        
        if overwrite:
            _headers = [None] * len(headers)
        else:
            _headers = [None] * len(set(headers).union(set(self.headers) if self.headers else set()))
            for header_idx, header_name in enumerate(self.headers):
                _headers[header_idx] = header_name
            
        for header_idx, header_name in enumerate(headers):
            if overwrite:
                self._set_buffer_cells(python_row_idx=start_row_idx,
                                       python_col_idx=header_idx,
                                       value=header_name)
                _headers[header_idx] = header_name
            else:
                if self.headers and header_name in self.headers:
                    header_original_idx = self.headers.index(header_name)
                    _headers[header_original_idx] = header_name
                    
                else:
                    self._set_buffer_cells(python_row_idx=start_row_idx,
                                       python_col_idx=current_header_idx,
                                       value=header_name)
                    _headers[current_header_idx] = header_name
                    current_header_idx += 1
        current_row_idx += 1
        headers = _headers
        logging.debug(f"Headers written starting at row {start_row_idx}")
        return current_row_idx, headers

    @GSheetManager.batch_sync_with_remote
    def _write_batch(self, data_list_batch, headers, start_row_idx):
        current_row_idx = start_row_idx
        for row_idx, d in enumerate(data_list_batch):
            for header_idx, header_name in enumerate(headers):
                if header_name in d:
                    self._set_buffer_cells(python_row_idx=start_row_idx + row_idx,
                                           python_col_idx=header_idx,
                                           value=d[header_name])
            current_row_idx += 1
        logging.debug(f"Batch of {len(data_list_batch)} rows written starting at row {start_row_idx}")
        return current_row_idx

    @GSheetManager.batch_sync_with_remote
    def write_rows(self, rows, empty_sheet=False, headers=None, write_headers=True, start_row_idx=0, batch_size=1000, index_col=None, overwrite_headers=False):
        if empty_sheet:
            self.clear_worksheet()
            logging.info("Sheet emptied before writing")

        if headers is None:
            headers = self.headers

        if write_headers:
            current_row_idx, headers = self._write_headers(headers, start_row_idx=start_row_idx, overwrite=overwrite_headers)
        else:
            current_row_idx = start_row_idx
            
        if index_col is not None:
            index_col_idx = self.headers.index(index_col)
            indices = [row[index_col_idx] for row in self.local_sheet_values[1:]]
            if not indices[-1]:
                indices = indices[:-1]
            indices = [int(index) for index in indices]
            rows_dict = {row[index_col]: row for row in rows}
            rows = [rows_dict[index] for index in indices]
            
        total_rows = len(rows)
        for idx in tqdm.tqdm(range(0, total_rows, batch_size)):
            current_row_idx = self._write_batch(data_list_batch=rows[idx:idx + batch_size],
                                                headers=headers, start_row_idx=current_row_idx)
        logging.info(f"Total of {total_rows} rows written to sheet")
        return current_row_idx

    @GSheetManager.batch_sync_with_remote
    def write_cells(self, where, what, overwrite=False):
        updates_count = 0
        for where_, what_ in zip(where, what):
            try:
                python_row_idx = next(i for i, row in enumerate(self.local_sheet_values) 
                              if all(row[self.headers.index(k)] == v for k, v in where_.items()))
            except StopIteration:
                logging.warning(f"No matching row found for conditions: {where_}")
                continue
            
            for col_header, value in what_.items():
                try:
                    python_col_idx = self.headers.index(col_header)
                except ValueError:
                    logging.warning(f"Column header '{col_header}' not found in headers")
                    continue
                
                current_value = self.local_sheet_values[python_row_idx][python_col_idx]
                if current_value and current_value != value and not overwrite:
                    logging.warning(f"Skipping non-empty cell at row {python_row_idx + 1}, column {col_header}. Current value: '{current_value}', New value: '{value}'")
                    continue
                
                if current_value and current_value != value and overwrite:
                    logging.info(f"Overwriting cell at row {python_row_idx + 1}, column {col_header}. Old value: '{current_value}', New value: '{value}'")
                
                self._set_buffer_cells(python_row_idx=python_row_idx,
                                       python_col_idx=python_col_idx, 
                                       value=value)
                updates_count += 1
                
        logging.info(f"Updated {updates_count} cells in the sheet")