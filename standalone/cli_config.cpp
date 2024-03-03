//
// Copyright (c) 2022 alandefreitas (alandefreitas@gmail.com)
//
// Distributed under the Boost Software License, Version 1.0.
// https://www.boost.org/LICENSE_1_0.txt
//

#include "cli_config.hpp"
#include <boost/asio.hpp>
#include <boost/process/v2.hpp>
#include <boost/program_options.hpp>
#include <fmt/color.h>
#include <fmt/format.h>
#include <fmt/ostream.h>
#include <fmt/ranges.h>
#include <algorithm>
#include <charconv>

#if FMT_VERSION >= 90000
template <>
struct fmt::formatter<boost::program_options::options_description>
    : ostream_formatter {};
template <>
struct fmt::formatter<std::filesystem::path> : ostream_formatter {};
#endif

namespace fs = std::filesystem;
namespace basio = boost::asio;
namespace process = boost::process::v2;

void
print_help(const boost::program_options::options_description &desc) {
    fmt::print("{}\n", desc);
}

boost::program_options::options_description &
program_description() {
    namespace fs = std::filesystem;
    namespace po = boost::program_options;
    static po::options_description desc("clang-unformat");
    // clang-format off
    const fs::path empty_path;
    if (desc.options().empty()) {
        desc.add_options()
        ("help", "produce help message")
        ("input", po::value<fs::path>()->default_value(empty_path), "input directory with source files")
        ("output", po::value<fs::path>()->default_value(empty_path), "output path for the clang-format file")
        ("temp", po::value<fs::path>()->default_value(empty_path), "temporary directory to formatted source files")
        ("clang-format", po::value<fs::path>()->default_value(empty_path), "path to the clang-format executable")
        ("parallel", po::value<std::size_t>()->default_value(std::max(std::thread::hardware_concurrency(), static_cast<unsigned int>(1))), "number of threads")
        ("require-influence", po::value<bool>()->default_value(false), "only include parameters that influence the output")
        ("extensions", po::value<std::vector<std::string>>(), "file extensions to format");
    }
    // clang-format on
    return desc;
}

cli_config
parse_cli(int argc, char **argv) {
    namespace fs = std::filesystem;
    namespace po = boost::program_options;
    po::variables_map vm;
    po::store(po::parse_command_line(argc, argv, program_description()), vm);
    po::notify(vm);
    cli_config c;
    c.help = vm.count("help");
    c.input = vm["input"].as<fs::path>();
    c.output = vm["output"].as<fs::path>();
    c.temp = vm["temp"].as<fs::path>();
    c.clang_format = vm["clang-format"].as<fs::path>();
    if (vm.count("extensions")) {
        c.extensions = vm["extensions"].as<std::vector<std::string>>();
    }
    c.parallel = vm["parallel"].as<std::size_t>();
    c.require_influence = vm["require-influence"].as<bool>();
    return c;
}

bool
equal_directory_layout(const fs::path &temp, const fs::path &input) {
    auto begin = fs::recursive_directory_iterator(input);
    auto end = fs::recursive_directory_iterator{};
    for (auto it = begin; it != end; ++it) {
        fs::path input_relative = fs::relative(*it, input);
        fs::path output_relative = temp / input_relative;
        if (!fs::exists(output_relative)) {
            return false;
        }
    }
    return true;
}

bool
equal_subdirectory_layout(const fs::path &temp, const fs::path &input) {
    auto begin = fs::directory_iterator(temp);
    auto end = fs::directory_iterator{};
    for (auto it = begin; it != end; ++it) {
        auto const &p = *it;
        if (!fs::is_directory(p) || !equal_directory_layout(p, input)) {
            return false;
        }
    }
    return true;
}

bool
validate_input_dir(cli_config const &config) {
    fmt::print(fmt::fg(fmt::terminal_color::blue), "## Validating input\n");
    if (config.input.empty()) {
        fmt::print(
            fmt::fg(fmt::terminal_color::red),
            "Input directory not provided\n");
        return false;
    }
    if (!fs::exists(config.input)) {
        fmt::print(
            fmt::fg(fmt::terminal_color::red),
            "Input {} is does not exist",
            config.input);
        return false;
    }
    if (!fs::is_directory(config.input)) {
        fmt::print(
            fmt::fg(fmt::terminal_color::red),
            "Input {} is not a directory",
            config.input);
        return false;
    }
    fmt::print(
        fmt::fg(fmt::terminal_color::green),
        "config \"input\" {} OK!\n",
        config.input);
    fmt::print("\n");
    return true;
}

bool
validate_output_dir(cli_config &config) {
    fmt::print(fmt::fg(fmt::terminal_color::blue), "## Validating output\n");
    if (config.output.empty()) {
        fmt::print("No output path set\n");
        config.output = config.input / ".clang-format";
        fmt::print(
            fmt::fg(fmt::terminal_color::yellow),
            "output path set to {}\n",
            config.output);
    }
    if (fs::exists(config.output)) {
        fmt::print("output path {} already exists\n", config.output);
        if (fs::is_directory(config.output)) {
            fmt::print(
                fmt::fg(fmt::terminal_color::yellow),
                "output {} is a directory\n",
                config.output);
            config.output /= ".clang-format";
            fmt::print(
                fmt::fg(fmt::terminal_color::yellow),
                "output set to {}\n",
                config.output);
            return false;
        }
    }
    if (config.output.filename() != ".clang-format") {
        fmt::print(
            fmt::fg(fmt::terminal_color::red),
            "output file {} should be .clang-format\n",
            config.output);
        return false;
    }
    if (!fs::exists(config.output)) {
        fmt::print(
            fmt::fg(fmt::terminal_color::blue),
            "output file {} doesn't exist yet\n",
            config.output);
    }
    fmt::print(
        fmt::fg(fmt::terminal_color::green),
        "config \"output\" {} OK!\n",
        config.output);
    fmt::print("\n");
    return true;
}

bool
validate_temp_dir(cli_config &config) {
    fmt::print(fmt::fg(fmt::terminal_color::blue), "## Validating temp\n");
    if (config.temp.empty()) {
        fmt::print("No temp directory set\n");
        config.temp = fs::current_path() / "clang-unformat-temp";
        fmt::print(
            fmt::fg(fmt::terminal_color::yellow),
            "temp directory set to {}\n",
            config.temp);
    }
    if (fs::exists(config.temp)) {
        fmt::print(
            fmt::fg(fmt::terminal_color::yellow),
            "temp directory {} already exists\n",
            config.temp);
        if (!fs::is_directory(config.temp)) {
            fmt::print(
                fmt::fg(fmt::terminal_color::red),
                "temp {} is not a directory\n",
                config.temp);
            return false;
        }
        auto n_files = std::distance(
            fs::directory_iterator(config.temp),
            fs::directory_iterator{});
        if (n_files) {
            if (equal_directory_layout(config.temp, config.input)
                || equal_subdirectory_layout(config.temp, config.input))
            {
                fmt::print(
                    "temp directory {} is not empty but has an valid directory "
                    "layout\n",
                    config.temp);
            } else {
                fmt::print(
                    fmt::fg(fmt::terminal_color::red),
                    "temp directory {} cannot be used\n",
                    config.temp);
                return false;
            }
        }
    } else {
        fs::create_directories(config.temp);
        fmt::print(
            fmt::fg(fmt::terminal_color::green),
            "temp directory {} created\n",
            config.temp);
    }
    fmt::print(
        fmt::fg(fmt::terminal_color::green),
        "config \"temp\" {} OK!\n",
        config.temp);
    fmt::print("\n");
    return true;
}

// store the clang format version for future error messages
// we run clang-format --version with boost::process to extract the version
bool
set_clang_format_version(cli_config &config) {
    fmt::print(
        fmt::fg(fmt::terminal_color::yellow),
        "default to {}\n",
        config.clang_format);
    bool success = false;
    basio::io_context proc_ctx;
    basio::readable_pipe rp{ proc_ctx };
    basio::streambuf buffer;
    basio::cancellation_signal sig;
    process::async_execute(
        process::process(
            proc_ctx,
            config.clang_format.c_str(),
            { "--version" },
            process::process_stdio{ nullptr, rp, nullptr }),
        basio::bind_cancellation_slot(
            sig.slot(),
            [&](boost::system::error_code ec, int exit_code) {
        if (ec || exit_code) {
            fmt::print(
                stderr,
                "clang-format --version got error: {} ret val: {}\n",
                ec.message(),
                exit_code);
            success = false;
        }
        fmt::print(
            stderr,
            "clang-format --version got NO error: {} ret val: {}\n",
            ec.message(),
            exit_code);
    }));

    std::string line;
    auto read_cb_inner =
        [&config,
         &success,
         &line,
         &buffer,
         &rp](boost::system::error_code ec, std::size_t n, auto &&read_cb_inner)
        -> void {
        if (ec) {
            if (ec != basio::error::eof) {
                fmt::print(
                    fmt::fg(fmt::terminal_color::red),
                    "boost error in set_clang_format_version! {}\n",
                    ec.message());
            } else {
                success = false;
            }
            return;
        }
        std::string_view::size_type major_end;
        std::string_view needle{ "clang-format version " };
        std::string_view clang_version_view;
        std::size_t clang_version_off;
        std::size_t major = 0;
        std::from_chars_result res{};
        std::istream is(&buffer);
        std::getline(is, line);
        if (line.empty()) {
            return;
        }
        fmt::print(fmt::fg(fmt::terminal_color::green), "{}\n", line);
        std::string_view line_view(line);
        // find line with version
        if (!(clang_version_off = line_view.find(needle)))
            goto next_read;

        line_view = line_view.substr(
            clang_version_off + needle.size(),
            line_view.size());

        // find version major in the line
        major_end = line_view.find_first_of('.');
        if (major_end == std::string_view::npos) {
            fmt::print(
                fmt::fg(fmt::terminal_color::red),
                "Cannot find major version in \"{}\"\n",
                line);
            success = false;
            return;
        }

        // convert the major string to major int
        clang_version_view = line_view.substr(0, major_end);
        res = std::from_chars(
            clang_version_view.data(),
            clang_version_view.data() + clang_version_view.size(),
            major,
            10);
        if (res.ec != std::errc{}) {
            fmt::print(
                fmt::fg(fmt::terminal_color::red),
                "Cannot parse major version \"{}\" as integer\n",
                clang_version_view);
            success = false;
            return;
        }

        config.clang_format_version = major;
        if (major < 13) {
            fmt::print(
                fmt::fg(fmt::terminal_color::red),
                "You might want to update clang-format from {} for this to "
                "work properly\n",
                major);
        }
        success = true;
        return;

    next_read:
        basio::async_read_until(
            rp,
            buffer,
            '\n',
            [&read_cb_inner](boost::system::error_code ec, std::size_t n) {
            return read_cb_inner(ec, n, read_cb_inner);
        });
    };
    basio::async_read_until(
        rp,
        buffer,
        '\n',
        [&read_cb_inner](boost::system::error_code ec, std::size_t n) {
        return read_cb_inner(ec, n, read_cb_inner);
    });
    proc_ctx.run();
    return success;
}

bool
validate_clang_format_executable(cli_config &config) {
    fmt::print(
        fmt::fg(fmt::terminal_color::blue),
        "## Validating clang-format\n");
    if (config.clang_format.empty()) {
        fmt::print("no clang-format path set\n");
        config.clang_format
            = process::environment::find_executable("clang-format").c_str();
        if (fs::exists(config.clang_format)) {
            set_clang_format_version(config);
        } else {
            fmt::print(
                fmt::fg(fmt::terminal_color::red),
                "cannot find clang-format in PATH\n");
            return false;
        }
    } else if (!fs::exists(config.clang_format)) {
        fmt::print(
            fmt::fg(fmt::terminal_color::red),
            "cannot find clang-format in path {}\n",
            config.clang_format);
        return false;
    }
    set_clang_format_version(config);
    fmt::print(
        fmt::fg(fmt::terminal_color::green),
        "config \"clang_format\" {} OK! Major version: {}\n",
        config.clang_format,
        config.clang_format_version);
    fmt::print("\n");
    return true;
}

bool
validate_file_extensions(cli_config &config) {
    fmt::print(
        fmt::fg(fmt::terminal_color::blue),
        "## Validating file extensions\n");
    if (config.extensions.empty()) {
        fmt::print("no file extensions set\n");
        config.extensions = { "h", "hpp", "cpp", "ipp" };
        fmt::print(
            fmt::fg(fmt::terminal_color::yellow),
            "default to: {}\n",
            config.extensions);
    }
    fmt::print(
        fmt::fg(fmt::terminal_color::green),
        "config \"extensions\" {} OK!\n",
        config.extensions);
    fmt::print("\n");
    return true;
}

bool
validate_threads(cli_config &config) {
    fmt::print(fmt::fg(fmt::terminal_color::blue), "## Validating threads\n");
    if (config.parallel == 0) {
        fmt::print(
            fmt::fg(fmt::terminal_color::yellow),
            "Cannot execute with {} threads\n",
            config.parallel);
        config.parallel = std::
            max(std::thread::hardware_concurrency(),
                static_cast<unsigned int>(1));
        fmt::print(
            fmt::fg(fmt::terminal_color::yellow),
            "Defaulting to {} threads\n",
            config.parallel);
    }
    fmt::print(
        fmt::fg(fmt::terminal_color::green),
        "config \"parallel\" {} OK!\n",
        config.parallel);
    fmt::print("\n");
    return true;
}

bool
validate_config(cli_config &config) {
    namespace fs = std::filesystem;
#define CHECK(expr) \
    if (!(expr))    \
    return false
    CHECK(validate_input_dir(config));
    CHECK(validate_output_dir(config));
    CHECK(validate_temp_dir(config));
    CHECK(validate_clang_format_executable(config));
    CHECK(validate_file_extensions(config));
    CHECK(validate_threads(config));
#undef CHECK
    fmt::print("=============================\n\n");
    return true;
}
