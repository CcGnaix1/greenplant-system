package com.greenplant;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.greenplant.mapper")
public class GreenplantApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreenplantApplication.class, args);
    }
}
